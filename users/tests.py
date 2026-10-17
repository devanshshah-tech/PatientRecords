import tempfile
import uuid
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from PIL import Image
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, AnonymousUser
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .access import can_submit
from .adapters import ClosedAccountAdapter, InvitedSocialAdapter
from .admin import AccessForm
from .models import Patient, Visit, Photo, InternAccess, AuditEvent, one_year_from_now
from .services import compress_photos, save_submission


def synthetic_photo(size=(64, 64), exif=None):
    output = BytesIO()
    image = Image.new('RGB', size, (120, 160, 180))
    image.save(output, 'JPEG', **({'exif': exif} if exif else {}))
    return SimpleUploadedFile('synthetic.jpg', output.getvalue(), content_type='image/jpeg')


def submission(**kwargs):
    return {'submission_id': str(uuid.uuid4()), 'patient_id': 'TEST-001', 'consent_confirmed': True,
        'opd_number': 'OPD-1', 'case_year': '2026', 'name_of_patient': 'Synthetic patient',
        'age': 25, 'gender': 'O', 'diagnosis': 'Synthetic injury', 'name_of_intern': 'Synthetic intern',
        'roll_number': '1', **kwargs}


@override_settings(STORAGES={'default': {'BACKEND': 'users.storage.PrivateFileStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ClinicalWorkflowTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.intern = get_user_model().objects.create_user('intern', email='intern@example.test')
        EmailAddress.objects.create(user=self.intern, email=self.intern.email, verified=True, primary=True)
        self.grant = InternAccess.objects.create(email=self.intern.email, reason='Synthetic semester')
        self.doctor = get_user_model().objects.create_user('doctor')
        self.doctor.user_permissions.add(Permission.objects.get(codename='compare_patients'))
        self.client.force_login(self.intern)

    def create_visit(self, **kwargs):
        return save_submission(self.intern, submission(**kwargs), compress_photos([synthetic_photo()]))

    def test_unlisted_and_unverified_users_cannot_submit(self):
        self.assertFalse(can_submit(AnonymousUser()))
        EmailAddress.objects.filter(user=self.intern).update(verified=False)
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 403)
        EmailAddress.objects.filter(user=self.intern).update(verified=True)
        self.grant.delete()
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 403)

    def test_revocation_rechecks_existing_session(self):
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 200)
        self.grant.revoked = True
        self.grant.save()
        self.assertEqual(self.client.post(reverse('submit_patient_details'), submission()).status_code, 403)

    def test_expiry_and_extension(self):
        self.grant.starts_at = timezone.now() - timedelta(days=400)
        self.grant.expires_at = timezone.now() - timedelta(seconds=1)
        self.grant.save()
        self.assertFalse(can_submit(self.intern))
        self.grant.expires_at = timezone.now() + timedelta(days=60)
        self.grant.save()
        self.assertTrue(can_submit(self.intern))

    def test_future_grant_denied(self):
        self.grant.starts_at = timezone.now() + timedelta(days=1)
        self.grant.save()
        self.assertFalse(can_submit(self.intern))

    def test_staff_without_doctor_permission_cannot_review(self):
        self.intern.is_staff = True
        self.intern.save()
        self.assertEqual(self.client.get(reverse('comparison')).status_code, 403)
        self.assertEqual(self.client.get(reverse('doctor_search')).status_code, 403)

    def test_photos_private_and_no_public_url(self):
        photo = self.create_visit().photos.get()
        url = reverse('private_photo', args=[photo.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.doctor)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        # Consume through Django's test-client wrapper so request-finished cleanup
        # does not close the PostgreSQL transaction shared by this TestCase class.
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\xff\xd8'))
        self.assertTrue(response.closed)
        with self.assertRaises(ValueError):
            _ = photo.image.url
        self.assertEqual(self.client.get('/media/' + photo.image.name).status_code, 404)

    def test_consent_required_on_server(self):
        data = submission(consent_confirmed=False)
        data['patient_images'] = synthetic_photo()
        response = self.client.post(reverse('submit_patient_details'), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Visit.objects.exists())
        with self.assertRaises(ValidationError):
            save_submission(self.intern, submission(consent_confirmed=False), [b'abc'])

    def test_successful_submission_stores_identity_and_never_emails(self):
        data = submission()
        data.pop('opd_number')  # Aadhar/ABHA is optional, including a missing POST key.
        data['patient_images'] = synthetic_photo()
        with patch('django.core.mail.EmailMessage.send') as send:
            response = self.client.post(reverse('submit_patient_details'), data)
        self.assertEqual(response.status_code, 302)
        send.assert_not_called()
        visit = Visit.objects.get()
        self.assertEqual(visit.opd_number, '')
        self.assertEqual(visit.submitted_by, self.intern)
        self.assertTrue(visit.consent_confirmed)
        self.assertEqual(visit.patient.photo_bytes, visit.photos.get().size_bytes)
        self.assertTrue(AuditEvent.objects.filter(action='submission').exists())

    @override_settings(CLINICAL_UPLOADS_ENABLED=False, PREVIEW_MODE=True)
    def test_preview_camera_page_cannot_persist_visits(self):
        page = self.client.get(reverse('submit_patient_details'))
        self.assertContains(page, 'Camera preview is available')
        self.assertContains(page, 'data-uploads-enabled="false"')
        data = submission()
        data['patient_images'] = synthetic_photo()
        response = self.client.post(reverse('submit_patient_details'), data)
        self.assertContains(response, 'Saving visits is disabled')
        self.assertFalse(Visit.objects.exists())
        self.assertFalse(Photo.objects.exists())
        with self.assertRaises(ValidationError):
            self.create_visit()

    @override_settings(PHOTO_STORAGE='drive')
    def test_drive_upload_reference_is_saved_and_failure_rolls_back(self):
        from .drive_storage import DriveStorageError
        storage_settings = {'default': {'BACKEND': 'users.drive_storage.PrivateDriveStorage',
            'OPTIONS': {'credentials_file': 'synthetic.json', 'root_folder_id': 'synthetic_root'}},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        with override_settings(STORAGES=storage_settings), \
                patch('users.drive_storage.authorized_session'), \
                patch('users.drive_storage.PrivateDriveStorage._folder', return_value='synthetic_folder'), \
                patch('users.drive_storage.PrivateDriveStorage._create', return_value='synthetic_file'):
            visit = self.create_visit()
            self.assertEqual(visit.photos.get().image.name, 'drive/synthetic_file')
        with override_settings(STORAGES=storage_settings), \
                patch('users.drive_storage.authorized_session'), \
                patch('users.drive_storage.PrivateDriveStorage._folder', return_value='synthetic_folder'), \
                patch('users.drive_storage.PrivateDriveStorage._create', side_effect=DriveStorageError('synthetic')):
            with self.assertRaises(DriveStorageError):
                self.create_visit(patient_id='SYNTHETIC-FAILED-DRIVE')
            self.assertFalse(Patient.objects.filter(patient_id='SYNTHETIC-FAILED-DRIVE').exists())

    def test_retry_does_not_duplicate_visit_or_quota(self):
        data = submission()
        blobs = compress_photos([synthetic_photo()])
        first = save_submission(self.intern, data, blobs)
        second = save_submission(self.intern, data, blobs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Patient.objects.get().photo_bytes, len(blobs[0]))

    def test_same_patient_links_multiple_visits(self):
        self.create_visit()
        self.create_visit()
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 2)

    @override_settings(PATIENT_PHOTO_QUOTA_BYTES=1)
    def test_quota_failure_rolls_back_record(self):
        with self.assertRaises(ValidationError):
            self.create_visit()
        self.assertFalse(Patient.objects.exists())
        self.assertFalse(Visit.objects.exists())

    def test_failure_cleans_up_files_and_quota(self):
        with patch.object(Photo, 'save', side_effect=RuntimeError('Synthetic disk/database failure')):
            with self.assertRaises(RuntimeError):
                self.create_visit()
        self.assertFalse(Patient.objects.exists())
        self.assertFalse(Visit.objects.exists())
        self.assertFalse(any(p.is_file() for p in Path(self.media.name).rglob('*')))

    def test_resize_orientation_and_metadata_stripping(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'Synthetic metadata'
        data = compress_photos([synthetic_photo((3000, 1000), exif)])[0]
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.height, 2048)
            self.assertLess(result.width, result.height)
            self.assertEqual(len(result.getexif()), 0)

    def test_corrupt_images_rejected(self):
        with self.assertRaises(ValidationError):
            compress_photos([SimpleUploadedFile('spoof.jpg', b'not an image', content_type='image/jpeg')])

    def test_missing_and_excessive_photos_rejected(self):
        for photos in ([], [synthetic_photo() for _ in range(11)]):
            with self.assertRaises(ValidationError):
                compress_photos(photos)

    @override_settings(MAX_IMAGE_BYTES=5)
    def test_image_size_enforced_during_multipart_parse(self):
        data = submission()
        data['patient_images'] = synthetic_photo()
        self.assertEqual(self.client.post(reverse('submit_patient_details'), data).status_code, 400)
        self.assertFalse(Visit.objects.exists())

    def test_animated_images_rejected(self):
        output = BytesIO()
        Image.new('RGB', (10, 10)).save(output, 'PNG', save_all=True,
            append_images=[Image.new('RGB', (10, 10), 'red')], duration=10)
        with self.assertRaises(ValidationError):
            compress_photos([SimpleUploadedFile('animated.png', output.getvalue())])

    def test_doctor_search_and_comparison(self):
        first = self.create_visit()
        second = self.create_visit()
        other = self.create_visit(patient_id='OTHER')
        self.client.force_login(self.doctor)
        response = self.client.post(reverse('doctor_search'), {'opd_number': 'OPD-1', 'diagnosis': 'injury'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['visits']), 3)
        response = self.client.post(reverse('comparison'), {'patient_id': 'TEST-001',
            'photos': [str(first.photos.get().pk), str(second.photos.get().pk)]})
        self.assertEqual(len(response.context['selected']), 2)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        response = self.client.post(reverse('comparison'), {'patient_id': 'TEST-001', 'photos': [str(other.photos.get().pk)]})
        self.assertEqual(response.context['selected'], [])
        response = self.client.post(reverse('comparison'), {'patient_id': 'TEST-001', 'photos': ['x' * 36]})
        self.assertEqual(response.status_code, 200)

    def test_google_invitation_requires_verified_email(self):
        login = SocialLogin(user=get_user_model()(username='new'),
            account=SocialAccount(provider='google', uid='synthetic'),
            email_addresses=[EmailAddress(email=self.intern.email, verified=False)])
        adapter = InvitedSocialAdapter()
        self.assertFalse(adapter.allowed(login))
        login.email_addresses[0].verified = True
        self.assertTrue(adapter.allowed(login))
        self.grant.revoked = True
        self.grant.save()
        self.assertFalse(adapter.allowed(login))
        self.assertFalse(ClosedAccountAdapter().is_open_for_signup(None))

    def test_rejected_google_account_has_clean_retry_route_without_creating_user(self):
        from allauth.core.exceptions import ImmediateHttpResponse
        login = SocialLogin(user=get_user_model()(username='not-invited'),
            account=SocialAccount(provider='google', uid='not-invited'),
            email_addresses=[EmailAddress(email='not-invited@example.test', verified=True)])
        before = get_user_model().objects.count()
        with self.assertRaises(ImmediateHttpResponse) as rejected:
            InvitedSocialAdapter().pre_social_login(None, login)
        self.assertEqual(rejected.exception.response.url, reverse('access_denied'))
        self.client.logout()
        response = self.client.get(reverse('access_denied'))
        self.assertContains(response, 'Try another Google account', status_code=403)
        self.assertContains(response, 'csrfmiddlewaretoken', status_code=403)
        self.assertContains(response, reverse('google_login'), status_code=403)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(get_user_model().objects.count(), before)
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 302)
        response = self.client.post(reverse('google_login'))
        self.assertEqual(response.status_code, 302)
        from urllib.parse import urlsplit, parse_qs
        self.assertEqual(parse_qs(urlsplit(response.url).query)['prompt'], ['select_account'])

    def test_preprovisioned_doctor_requires_verified_matching_google_identity(self):
        self.doctor.email = 'synthetic.doctor@gmail.com'
        self.doctor.save()
        login = SocialLogin(user=get_user_model()(username='new'),
            account=SocialAccount(provider='google', uid='synthetic-bootstrap'),
            email_addresses=[EmailAddress(email=self.doctor.email, verified=True)])
        login.lookup()
        self.assertTrue(login.is_existing)
        self.assertEqual(login.user.pk, self.doctor.pk)
        self.assertTrue(InvitedSocialAdapter().allowed(login))

    def test_workspace_doctor_bootstrap_requires_hosted_domain_and_verified_email(self):
        self.doctor.email = 'doctor@clinic.example.test'
        self.doctor.save()
        login = SocialLogin(user=get_user_model()(username='new-workspace'),
            account=SocialAccount(provider='google', uid='synthetic-workspace',
                extra_data={'hd': 'clinic.example.test'}),
            email_addresses=[EmailAddress(email=self.doctor.email, verified=True)])
        adapter = InvitedSocialAdapter()
        self.assertTrue(adapter.can_authenticate_by_email(login, self.doctor.email))
        login.lookup()
        self.assertEqual(login.user.pk, self.doctor.pk)
        adapter.pre_social_login(None, login)
        self.assertTrue(EmailAddress.objects.filter(user=self.doctor, verified=True).exists())
        login.account.extra_data = {}
        self.assertFalse(adapter.can_authenticate_by_email(login, self.doctor.email))
        login.account.extra_data = {'hd': 'clinic.example.test'}
        login.email_addresses[0].verified = False
        self.assertFalse(adapter.can_authenticate_by_email(login, self.doctor.email))

    def test_precreated_intern_retains_google_verification_for_protected_requests(self):
        user = get_user_model().objects.create_user('precreated', email='precreated@gmail.com')
        grant = InternAccess.objects.create(email=user.email, reason='Synthetic preauthorization')
        login = SocialLogin(user=get_user_model()(username='new'),
            account=SocialAccount(provider='google', uid='precreated-google',
                extra_data={'given_name': 'Synthetic', 'family_name': 'Intern'}),
            email_addresses=[EmailAddress(email=user.email, verified=True)])
        login.lookup()
        self.assertEqual(login.user.pk, user.pk)
        self.assertFalse(can_submit(user))
        InvitedSocialAdapter().pre_social_login(None, login)
        user.refresh_from_db()
        self.assertEqual(user.get_full_name(), 'Synthetic Intern')
        self.assertTrue(EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists())
        self.assertTrue(can_submit(user))
        self.client.force_login(user)
        home = self.client.get(reverse('index'))
        self.assertContains(home, 'Synthetic Intern')
        self.assertContains(home, '(Intern)')
        from django.template.loader import render_to_string
        notification = render_to_string('account/messages/logged_in.txt', {'user': user})
        self.assertIn('Synthetic Intern (Intern)', notification)
        self.assertNotIn(user.username, notification)
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 200)
        self.assertEqual(self.client.get(reverse('doctor_search')).status_code, 403)
        grant.revoked = True
        grant.save()
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 403)

    def test_unverified_google_login_cannot_create_local_verified_email(self):
        user = get_user_model().objects.create_user('unverified-bootstrap', email='unverified@gmail.com')
        InternAccess.objects.create(email=user.email, reason='Synthetic preauthorization')
        login = SocialLogin(user=user, account=SocialAccount(provider='google', uid='unverified-google'),
            email_addresses=[EmailAddress(email=user.email, verified=False)])
        from allauth.core.exceptions import ImmediateHttpResponse
        with self.assertRaises(ImmediateHttpResponse):
            InvitedSocialAdapter().pre_social_login(None, login)
        self.assertFalse(EmailAddress.objects.filter(user=user, verified=True).exists())

    def test_google_verification_does_not_reassign_another_accounts_email(self):
        user = get_user_model().objects.create_user('conflicting-bootstrap', email='conflict@gmail.com')
        InternAccess.objects.create(email=user.email, reason='Synthetic preauthorization')
        EmailAddress.objects.create(user=self.intern, email=user.email, verified=True)
        login = SocialLogin(user=user, account=SocialAccount(provider='google', uid='conflict-google'),
            email_addresses=[EmailAddress(email=user.email, verified=True)])
        from allauth.core.exceptions import ImmediateHttpResponse
        with self.assertRaises(ImmediateHttpResponse):
            InvitedSocialAdapter().pre_social_login(None, login)
        self.assertFalse(EmailAddress.objects.filter(user=user, verified=True).exists())

    def test_operator_provisioning_separates_doctor_and_intern_without_verifying_email(self):
        output = StringIO()
        call_command('configure_local_access', doctor_email='bootstrap.doctor@gmail.com',
            intern_email='bootstrap.intern@gmail.com', stdout=output)
        doctor = get_user_model().objects.get(email='bootstrap.doctor@gmail.com')
        intern = get_user_model().objects.get(email='bootstrap.intern@gmail.com')
        self.assertTrue(doctor.is_staff)
        self.assertTrue(doctor.has_perm('users.compare_patients'))
        self.assertTrue(doctor.has_perm('users.change_internaccess'))
        self.assertFalse(intern.is_staff)
        self.assertFalse(intern.has_perm('users.compare_patients'))
        self.assertFalse(intern.has_usable_password())
        self.assertTrue(InternAccess.objects.filter(email=intern.email, revoked=False).exists())
        self.assertFalse(EmailAddress.objects.filter(user__in=[doctor, intern], verified=True).exists())

    def test_email_bootstrap_rejects_unverified_unlisted_ambiguous_and_other_providers(self):
        self.intern.email = 'synthetic.intern@gmail.com'
        self.intern.is_staff = True
        self.intern.save()
        login = SocialLogin(user=get_user_model()(username='new'),
            account=SocialAccount(provider='google', uid='synthetic-bootstrap'),
            email_addresses=[EmailAddress(email=self.intern.email, verified=True)])
        adapter = InvitedSocialAdapter()
        self.assertFalse(adapter.can_authenticate_by_email(login, self.intern.email))
        self.grant.email = self.intern.email
        self.grant.save()
        self.assertTrue(adapter.can_authenticate_by_email(login, self.intern.email))
        login.email_addresses[0].verified = False
        self.assertFalse(adapter.can_authenticate_by_email(login, self.intern.email))
        login.email_addresses[0].verified = True
        login.account.provider = 'untrusted'
        self.assertFalse(adapter.can_authenticate_by_email(login, self.intern.email))
        login.account.provider = 'google'
        get_user_model().objects.create_user('duplicate', email=self.intern.email)
        self.assertFalse(adapter.can_authenticate_by_email(login, self.intern.email))

    def test_admin_requires_reason_and_calendar_year_default(self):
        form = AccessForm(data={'email': 'new@example.test', 'starts_at': timezone.now(),
            'expires_at': one_year_from_now(), 'reason': '   '})
        self.assertFalse(form.is_valid())
        self.assertIn('reason', form.errors)
        with patch('users.models.timezone.now', return_value=timezone.datetime(2024, 2, 29, tzinfo=timezone.get_current_timezone())):
            self.assertEqual(one_year_from_now().day, 28)
            self.assertEqual(one_year_from_now().year, 2025)

    def test_entry_page_and_camera_form_render(self):
        self.assertContains(self.client.get(reverse('index')), 'New patient visit')
        self.client.logout()
        self.assertContains(self.client.get(reverse('index')), 'Sign in with Google')
        self.client.force_login(self.intern)
        response = self.client.get(reverse('submit_patient_details'))
        self.assertContains(response, 'camera.js')
        self.assertNotContains(response, 'type="file"')
        self.assertContains(response, 'name="submission_id"')

    def test_semester_invites_require_permission_and_preserve_existing_grants(self):
        url = reverse('admin:users_internaccess_invite')
        self.intern.is_staff = True
        self.intern.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.intern.user_permissions.add(Permission.objects.get(codename='add_internaccess'))
        original_expiry = self.grant.expires_at
        response = self.client.post(url, {'emails': 'INTERN@example.test\nnew@example.test\nNEW@example.test',
            'reason': 'Synthetic semester roster'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(InternAccess.objects.count(), 2)
        self.grant.refresh_from_db()
        self.assertEqual(self.grant.expires_at, original_expiry)
        self.assertEqual(AuditEvent.objects.filter(action='access_change').count(), 1)
        response = self.client.post(url, {'emails': 'invalid address', 'reason': 'Synthetic semester'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(InternAccess.objects.count(), 2)


@skipUnless(connection.vendor == 'postgresql', 'Concurrent quota verification requires PostgreSQL; covered in CI.')
class ConcurrentQuotaTests(TransactionTestCase):
    def test_two_concurrent_uploads_cannot_exceed_quota(self):
        user = get_user_model().objects.create_user('concurrent', email='concurrent@example.test')
        EmailAddress.objects.create(user=user, email=user.email, verified=True)
        InternAccess.objects.create(email=user.email, reason='Synthetic concurrency test')
        Patient.objects.create(patient_id='TEST-001')
        blob = compress_photos([synthetic_photo()])[0]
        barrier = Barrier(2)
        def upload():
            try:
                worker = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                save_submission(worker, submission(), [blob])
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media,
            PATIENT_PHOTO_QUOTA_BYTES=len(blob), STORAGES={'default': {'BACKEND': 'users.storage.PrivateFileStorage'}}):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: upload(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Patient.objects.get().photo_bytes, len(blob))
        self.assertEqual(Visit.objects.count(), 1)
