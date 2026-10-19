import uuid
import re
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from .case_numbers import ANAND, LOCATION_CHOICES, folder_words


def one_year_from_now():
    now = timezone.now()
    try:
        return now.replace(year=now.year + 1)
    except ValueError:
        return now.replace(year=now.year + 1, day=28)


def current_intern_batch():
    today = timezone.localdate()
    start = today.year if today.month >= 4 else today.year - 1
    return f'{start}-{start + 1}'


def validate_intern_batch(value):
    if not re.fullmatch(r'[0-9]{4}-[0-9]{4}', value or '') or int(value[5:]) != int(value[:4]) + 1:
        raise ValidationError('Enter consecutive batch years, for example 2026-2027.')


class InternAccess(models.Model):
    email = models.EmailField(unique=True)
    batch = models.CharField(max_length=9, default=current_intern_batch, validators=[validate_intern_batch], db_index=True)
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=one_year_from_now)
    revoked = models.BooleanField(default=False)
    reason = models.TextField(help_text='Required reason for granting, extending or revoking access.')

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='unique_intern_email_casefold'),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F('starts_at')), name='access_expiry_after_start')]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Patient(models.Model):
    patient_id = models.CharField(max_length=100)
    location = models.CharField(max_length=32, choices=LOCATION_CHOICES, default=ANAND)
    photo_bytes = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['location', 'patient_id'], name='unique_case_per_location')]
        permissions = [('compare_patients', 'Can review patient photographs and compare visits')]

    def __str__(self):
        return self.patient_id


class Visit(models.Model):
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    opd_number = models.CharField(max_length=100, db_index=True, blank=True)
    case_year = models.CharField(max_length=100, db_index=True)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='visits')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    visit_number = models.PositiveIntegerField(null=True, blank=True)
    patient_folder_name = models.CharField(max_length=410, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    consent_confirmed = models.BooleanField()
    details = models.JSONField()

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['-created_at', '-id'], name='visit_recent_timestamp_idx')]
        constraints = [models.UniqueConstraint(fields=['patient', 'visit_number'], name='unique_patient_visit_number')]


def photo_path(instance, filename):
    if getattr(settings, 'PHOTO_STORAGE', 'filesystem') == 'drive':
        visit = instance.visit
        folder = f'{visit.visit_number}_{folder_words(visit.details.get("diagnosis", ""))}_{folder_words(visit.details.get("name_of_intern", ""))}'
        return f'{visit.patient.location}/{visit.patient_folder_name}/{folder}/{uuid.uuid4().hex}.jpg'
    return f'photos/{uuid.uuid4().hex}.jpg'


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, related_name='photos')
    image = models.FileField(upload_to=photo_path)
    size_bytes = models.PositiveIntegerField()


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    action = models.CharField(max_length=50)
    object_id = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
