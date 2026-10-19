from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError, connection
from django.db.models import F, Max
from .case_numbers import ANAND, TF, normalize_case_number, folder_words
from .access import can_submit
from .models import Patient, Visit, Photo, AuditEvent


def compress_photos(files):
    if not 1 <= len(files) <= settings.MAX_PHOTOS_PER_VISIT:
        raise ValidationError('Capture between 1 and 10 photographs.')
    if sum(f.size for f in files) > settings.MAX_UPLOAD_BYTES:
        raise ValidationError('Total upload exceeds 25 MiB.')
    results = []
    for upload in files:
        if upload.size > settings.MAX_IMAGE_BYTES:
            raise ValidationError('Each photograph must be at most 10 MiB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                upload.seek(0)
                with Image.open(upload) as check:
                    if check.format not in ('JPEG', 'PNG', 'WEBP') or getattr(check, 'n_frames', 1) != 1:
                        raise ValidationError('Only single-frame JPEG, PNG or WebP photographs are accepted.')
                    if check.width * check.height > 20_000_000:
                        raise ValidationError('Photograph exceeds the 20 megapixel limit.')
                    check.verify()
                upload.seek(0)
                with Image.open(upload) as source:
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((2048, 2048))
                    output = BytesIO()
                    image.save(output, format='JPEG', quality=85, optimize=True)
                    results.append(output.getvalue())
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValidationError('Invalid or unsafe photograph. Please capture it again.') from exc
    return results


def save_submission(user, details, photos):
    if not settings.CLINICAL_UPLOADS_ENABLED:
        raise ValidationError('Saving visits is disabled while private storage is being prepared.')
    details = dict(details)
    details['patient_id'] = normalize_case_number(details['patient_id'], strict=True)
    if details.get('previous_opd_number'):
        details['previous_opd_number'] = normalize_case_number(details['previous_opd_number'], strict=True)
    location = TF if details.get('tf_shift') else ANAND
    written = []
    try:
        with transaction.atomic():
            if not can_submit(user):
                raise ValidationError('Your access has expired or been revoked.')
            if not details.get('consent_confirmed'):
                raise ValidationError('Patient consent is required.')
            existing = Visit.objects.filter(submission_id=details['submission_id']).first()
            if existing:
                if existing.submitted_by_id != user.pk or (existing.patient.patient_id != details['patient_id'] or existing.patient.location != location):
                    raise ValidationError('Invalid submission identifier.')
                return existing
            # Serialize same-location Drive folder creation across different patients.
            # Transaction-scoped PostgreSQL advisory locks work through pooling too.
            if (settings.PHOTO_STORAGE == 'drive' and connection.vendor == 'postgresql'
                    and not settings.DRIVE_LOCATION_FOLDER_IDS.get(location)):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [731420, 1 if location == ANAND else 2])
            patient, _ = Patient.objects.get_or_create(patient_id=details['patient_id'], location=location)
            Patient.objects.select_for_update().get(pk=patient.pk)
            # A simultaneous retry can have committed while waiting for this patient lock.
            existing = Visit.objects.filter(submission_id=details['submission_id']).first()
            if existing:
                if existing.submitted_by_id != user.pk or existing.patient_id != patient.pk:
                    raise ValidationError('Invalid submission identifier.')
                return existing
            size = sum(len(photo) for photo in photos)
            reserved = Patient.objects.filter(pk=patient.pk,
                photo_bytes__lte=settings.PATIENT_PHOTO_QUOTA_BYTES - size).update(photo_bytes=F('photo_bytes') + size)
            if not reserved:
                raise ValidationError('This patient has reached the photograph storage limit. Contact a doctor.')
            previous = Visit.objects.filter(patient=patient).order_by('visit_number', 'created_at', 'pk').first()
            visit_number = (Visit.objects.filter(patient=patient).aggregate(number=Max('visit_number'))['number'] or 0) + 1
            patient_folder = previous.patient_folder_name if previous else ''
            if not patient_folder:
                first_details = previous.details if previous else details
                patient_folder = f'{patient.patient_id}_{folder_words(first_details.get("name_of_patient", ""))}_{folder_words(first_details.get("diagnosis", ""))}'
            visit = Visit.objects.create(patient=patient, submitted_by=user, consent_confirmed=True,
                visit_number=visit_number, patient_folder_name=patient_folder,
                submission_id=details['submission_id'],
                opd_number=details['opd_number'], case_year=details['case_year'],
                details={k: v for k, v in details.items() if k not in ('patient_id', 'consent_confirmed', 'submission_id')})
            for data in photos:
                photo = Photo(visit=visit, size_bytes=len(data))
                photo.image.save('capture.jpg', ContentFile(data), save=False)
                written.append((photo.image.storage, photo.image.name))
                photo.save()
            AuditEvent.objects.create(actor=user, action='submission', object_id=str(visit.pk))
            return visit
    except Exception as error:
        for storage, name in written:
            storage.delete(name)
        if isinstance(error, IntegrityError):
            existing = Visit.objects.filter(submission_id=details['submission_id'], submitted_by=user,
                patient__patient_id=details['patient_id'], patient__location=location).first()
            if existing:
                return existing
        raise
