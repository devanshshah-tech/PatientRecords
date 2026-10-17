"""Operator-only account provisioning; never grants email verification."""
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from users.models import AuditEvent, InternAccess


class Command(BaseCommand):
    help = 'Provision an admin/doctor and a separate one-year intern invitation.'

    def add_arguments(self, parser):
        parser.add_argument('--doctor-email', required=True)
        parser.add_argument('--intern-email', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        doctor_email = options['doctor_email'].strip().lower()
        intern_email = options['intern_email'].strip().lower()
        for email in (doctor_email, intern_email):
            validate_email(email)
            if not email.endswith('@gmail.com'):
                raise CommandError('This bootstrap supports Google-verified Gmail accounts only.')
        if doctor_email == intern_email:
            raise CommandError('Doctor and intern must be separate accounts.')
        User = get_user_model()

        def account(email):
            matches = list(User.objects.filter(email__iexact=email)[:2])
            if len(matches) > 1:
                raise CommandError('Ambiguous account email; resolve duplicates before provisioning.')
            if matches:
                if not matches[0].is_active:
                    raise CommandError('An account is inactive; review it before provisioning.')
                return matches[0]
            return User.objects.create_user(username='account-' + uuid.uuid4().hex, email=email, password=None)

        doctor, intern = account(doctor_email), account(intern_email)
        if intern.is_staff or intern.is_superuser or intern.get_all_permissions():
            raise CommandError('Intern account already has permissions; review them before provisioning.')
        doctor.is_staff = True
        doctor.save(update_fields=['is_staff'])
        permissions = Permission.objects.filter(content_type__app_label='users',
            codename__in=['compare_patients', 'add_internaccess', 'change_internaccess',
                'view_internaccess', 'view_auditevent'])
        doctor.user_permissions.add(*permissions)
        grant, created = InternAccess.objects.get_or_create(email=intern_email,
            defaults={'reason': 'Operator-authorized local sign-in setup'})
        if grant.revoked:
            raise CommandError('Existing intern invitation is revoked; extend/reactivate explicitly.')
        AuditEvent.objects.create(actor=doctor, action='account_setup', object_id=str(doctor.pk),
            details={'intern_user_id': intern.pk, 'grant_id': grant.pk, 'grant_created': created,
                'reason': 'Operator-authorized admin/doctor and intern setup'})
        self.stdout.write(self.style.SUCCESS('Admin/doctor permissions and intern invitation configured. Existing grant dates preserved. Google must verify identity at login.'))
