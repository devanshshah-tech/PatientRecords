import logging
import uuid
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .access import can_review, can_submit
from .forms import PatientDetailsForm, DoctorSearchForm, ComparisonLookupForm
from .case_numbers import ANAND
from .models import Patient, Photo, AuditEvent, Visit
from .services import compress_photos, save_submission
from .identity import display_name, display_role
from .drive_storage import DriveStorageError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.urls import reverse
from django.db import DatabaseError


logger = logging.getLogger(__name__)


def record_save_failure(error):
    if isinstance(error, DriveStorageError):
        logger.warning("clinical_save_failed category=drive code=%s operation=%s http_status=%s",
            error.diagnostic_code, error.operation, error.http_status)
    elif isinstance(error, DatabaseError):
        names = {"DatabaseError", "OperationalError", "IntegrityError", "ProgrammingError", "DataError",
            "InternalError", "InterfaceError", "NotSupportedError"}
        name = type(error).__name__
        logger.warning("clinical_save_failed category=database code=%s", name if name in names else "DatabaseError")
    else:
        logger.warning("clinical_save_failed category=filesystem code=OSError")


@never_cache
@require_GET
def health(request):
    return HttpResponse('ok', content_type='text/plain')


@never_cache
def access_denied(request):
    return render(request, 'access_denied.html', status=403)


def index(request):
    submit, review = can_submit(request.user), can_review(request.user)
    return render(request, 'index.html', {'can_submit': submit, 'can_review': review,
        'display_name': display_name(request.user) if request.user.is_authenticated else '',
        'display_role': display_role(request.user) if request.user.is_authenticated else ''})


@login_required
@require_http_methods(['GET', 'POST'])
def doctor_search(request):
    if not can_review(request.user):
        raise PermissionDenied
    form = DoctorSearchForm(request.POST if request.method == 'POST' else None)
    visits = []
    searched = request.method == 'POST' and form.is_valid()
    if searched:
        query = Visit.objects.select_related('patient')
        for key, value in form.cleaned_data.items():
            if value:
                lookup = ('patient__patient_id' if key == 'patient_id' else 'patient__location') if key in ('patient_id', 'location') else (
                    key if key in ('opd_number', 'case_year') else f'details__{key}__icontains')
                query = query.filter(**{lookup: value})
        visits = list(query[:50])
        AuditEvent.objects.create(actor=request.user, action='record_search', object_id='', details={'fields': [k for k, v in form.cleaned_data.items() if v]})
    groups = {}
    for visit in visits:
        group = groups.setdefault(visit.patient_id, {'patient': visit.patient,
            'name': visit.details.get('name_of_patient', ''), 'visits': []})
        group['visits'].append(visit)
    return render(request, 'doctor_search.html', {'form': form, 'visits': visits,
        'patient_groups': list(groups.values()), 'searched': searched})


@login_required
@require_GET
def visit_detail(request, visit_id):
    if not can_review(request.user):
        raise PermissionDenied
    visit = get_object_or_404(Visit.objects.select_related('patient').prefetch_related('photos'), pk=visit_id)
    AuditEvent.objects.create(actor=request.user, action='visit_view', object_id=str(visit.pk))
    return render(request, 'visit_detail.html', {'visit': visit})


@login_required
@require_http_methods(['GET', 'POST'])
def submit_patient_details(request):
    if not can_submit(request.user):
        raise PermissionDenied('Your intern access is not active. Contact your administrator.')
    form = PatientDetailsForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            photos = compress_photos(request.FILES.getlist('patient_images'))
            visit = save_submission(request.user, form.cleaned_data, photos)
        except ValidationError as error:
            form.add_error(None, error)
        except (DriveStorageError, DatabaseError, OSError) as error:
            record_save_failure(error)
            form.add_error(None, "We couldn't save the visit and photos. Please try again. If this keeps happening, ask your administrator for help.")
        else:
            destination = reverse('submission_success', args=[visit.submission_id])
            if 'application/json' in request.headers.get('Accept', ''):
                return JsonResponse({'redirect_url': destination}, status=201)
            return redirect(destination)
    return render(request, 'patient_form.html', {'form': form})


@login_required
@require_GET
@never_cache
def submission_success(request, submission_id):
    if not can_submit(request.user):
        raise PermissionDenied
    visit = get_object_or_404(Visit.objects.select_related('patient'),
        submission_id=submission_id, submitted_by=request.user)
    return render(request, 'submission_success.html', {'visit': visit,
        'photo_count': visit.photos.count(), 'can_review': can_review(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def comparison(request):
    if not can_review(request.user):
        raise PermissionDenied
    patient = None
    selected = []
    photos = []
    comparison_error = ''
    searched = request.method == 'POST'
    lookup_data = request.POST.copy() if searched else None
    if lookup_data is not None and 'location' not in lookup_data:
        lookup_data['location'] = ANAND
    lookup_form = ComparisonLookupForm(lookup_data, initial={'location': ANAND})
    if searched and lookup_form.is_valid():
        patient = Patient.objects.filter(**lookup_form.cleaned_data).first()
        if patient:
            photos = Photo.objects.filter(visit__patient=patient).select_related('visit').order_by('visit__created_at', 'pk')
            try:
                ids = [uuid.UUID(i) for i in request.POST.getlist('photos')]
            except ValueError:
                ids = []
                comparison_error = 'Invalid photograph selection.'
            if ids:
                if len(ids) != 2 or len(set(ids)) != 2:
                    comparison_error = 'Select exactly two different photographs to compare.'
                else:
                    selected = list(photos.filter(pk__in=ids))
                    if len(selected) != 2:
                        selected = []
                        comparison_error = 'Both photographs must belong to this patient.'
            AuditEvent.objects.create(actor=request.user, action='comparison', object_id=str(patient.pk))
    return render(request, 'comparison.html', {'patient': patient, 'photos': photos, 'selected': selected,
        'searched': searched, 'comparison_error': comparison_error, 'lookup_form': lookup_form})


@login_required
@require_http_methods(['GET'])
def private_photo(request, photo_id):
    if not can_review(request.user):
        raise PermissionDenied
    photo = get_object_or_404(Photo, pk=photo_id)
    AuditEvent.objects.create(actor=request.user, action='photo_view', object_id=str(photo.pk))
    try:
        response = FileResponse(photo.image.open('rb'), content_type='image/jpeg')
    except DriveStorageError:
        return HttpResponse('Photo storage is temporarily unavailable. Please try again later.', status=503)
    response['Content-Disposition'] = 'inline; filename="clinical-photo.jpg"'
    return response
