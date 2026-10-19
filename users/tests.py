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
    return {'submission_id': str(uuid.uuid4()), 'patient_id': '000001', 'consent_confirmed': True,
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
                self.create_visit(patient_id='000003')
            self.assertFalse(Patient.objects.filter(patient_id='000003').exists())


    def test_save_service_refuses_an_empty_photo_queue(self):
        for photos in ([], [b'']):
            with self.assertRaises(ValidationError):
                save_submission(self.intern, submission(), photos)
        self.assertFalse(Patient.objects.exists())
        self.assertFalse(Visit.objects.exists())
        self.assertFalse(Photo.objects.exists())

    @override_settings(PHOTO_STORAGE='drive')
    def test_second_photo_upload_failure_rolls_back_entire_visit_and_quota(self):
        from .drive_storage import DriveStorageError
        storage_settings = {'default': {'BACKEND': 'users.drive_storage.PrivateDriveStorage',
            'OPTIONS': {'credentials_file': 'synthetic.json', 'root_folder_id': 'synthetic_root'}},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        for existing in (False, True):
            case = '000004' if existing else '000005'
            if existing:
                patient = Patient.objects.create(patient_id=case, photo_bytes=123)
            with override_settings(STORAGES=storage_settings), \
                    patch('users.drive_storage.authorized_session'), \
                    patch('users.drive_storage.PrivateDriveStorage._folder', return_value='synthetic_folder'), \
                    patch('users.drive_storage.PrivateDriveStorage._create',
                        side_effect=['first_synthetic_file', DriveStorageError('second upload failed')]), \
                    patch('users.drive_storage.PrivateDriveStorage.delete') as cleanup:
                with self.assertRaises(DriveStorageError):
                    save_submission(self.intern, submission(patient_id=case), [b'synthetic-photo-one', b'synthetic-photo-two'])
                cleanup.assert_called_once_with('drive/first_synthetic_file')
            self.assertFalse(Visit.objects.exists())
            self.assertFalse(Photo.objects.exists())
            self.assertFalse(AuditEvent.objects.filter(action='submission').exists())
            if existing:
                patient.refresh_from_db()
                self.assertEqual(patient.photo_bytes, 123)
            else:
                self.assertFalse(Patient.objects.filter(patient_id=case).exists())

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
        other = self.create_visit(patient_id='000002')
        self.client.force_login(self.doctor)
        response = self.client.post(reverse('doctor_search'), {'opd_number': 'OPD-1', 'diagnosis': 'injury'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['visits']), 3)
        self.assertEqual(len(response.context['patient_groups']), 2)
        self.assertContains(response, 'View this visit', count=3)
        self.assertContains(response, 'Compare across visits', count=2)
        response = self.client.post(reverse('comparison'), {'patient_id': '000001',
            'photos': [str(first.photos.get().pk), str(second.photos.get().pk)]})
        self.assertEqual(len(response.context['selected']), 2)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        response = self.client.post(reverse('comparison'), {'patient_id': '000001', 'photos': [str(other.photos.get().pk)]})
        self.assertEqual(response.context['selected'], [])
        response = self.client.post(reverse('comparison'), {'patient_id': '000001', 'photos': ['x' * 36]})
        self.assertEqual(response.status_code, 200)

    def test_single_visit_view_is_private_and_does_not_include_other_visit_photos(self):
        first = self.create_visit(age=24)
        second = self.create_visit(age=25)
        url = reverse('visit_detail', args=[first.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.doctor)
        response = self.client.get(url)
        self.assertContains(response, 'Age at visit: 24')
        self.assertContains(response, reverse('private_photo', args=[first.photos.get().pk]))
        self.assertNotContains(response, reverse('private_photo', args=[second.photos.get().pk]))
        self.assertEqual(response.headers['Cache-Control'], 'no-store, private')
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_fetch_success_message_survives_navigation_and_failures_preserve_form_errors(self):
        data = submission()
        data['patient_images'] = synthetic_photo()
        response = self.client.post(reverse('submit_patient_details'), data, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 201)
        destination = reverse('submission_success', args=[Visit.objects.get().submission_id])
        self.assertEqual(response.json(), {'redirect_url': destination})
        self.assertNotIn('messages', response.cookies)
        for _ in range(2):
            confirmation = self.client.get(destination)
            self.assertContains(confirmation, 'Visit added for Synthetic patient')
            self.assertContains(confirmation, '1 image uploaded successfully.')
            self.assertEqual(confirmation['Cache-Control'], 'no-store, private')
        invalid = submission(patient_id='')
        invalid['patient_images'] = synthetic_photo()
        response = self.client.post(reverse('submit_patient_details'), invalid, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)


    def test_confirmation_reports_actual_count_for_doctor_and_retries(self):
        self.client.force_login(self.doctor)
        data = submission(name_of_patient='<script>synthetic</script>')
        data['patient_images'] = [synthetic_photo() for _ in range(10)]
        saved = self.client.post(reverse('submit_patient_details'), data, HTTP_ACCEPT='application/json')
        self.assertEqual(saved.status_code, 201)
        confirmation = self.client.get(saved.json()['redirect_url'])
        self.assertContains(confirmation, '10 images uploaded successfully.')
        self.assertNotContains(confirmation, '<script>synthetic</script>')
        self.assertContains(confirmation, '&lt;script&gt;synthetic&lt;/script&gt;')
        data['patient_images'] = synthetic_photo()
        retried = self.client.post(reverse('submit_patient_details'), data)
        self.assertRedirects(retried, saved.json()['redirect_url'])
        self.assertContains(self.client.get(retried.url), '10 images uploaded successfully.')
        self.assertEqual(Visit.objects.count(), 1)
        self.client.force_login(self.intern)
        self.assertEqual(self.client.get(retried.url).status_code, 404)

    def test_confirmation_requires_current_access_and_original_uploader(self):
        visit = self.create_visit()
        url = reverse('submission_success', args=[visit.submission_id])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.intern)
        self.grant.revoked = True
        self.grant.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_save_failure_returns_plain_retry_message_without_exception_details(self):
        from django.db import OperationalError
        from .drive_storage import DriveStorageError
        for error in (DriveStorageError('technical storage detail'), OperationalError('technical database detail'), OSError('technical disk detail')):
            data = submission()
            data['patient_images'] = synthetic_photo()
            with patch('users.views.save_submission', side_effect=error):
                response = self.client.post(reverse('submit_patient_details'), data, HTTP_ACCEPT='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Please try again.')
            self.assertNotContains(response, 'technical')
            self.assertFalse(Visit.objects.exists())

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
            'reason': 'Synthetic semester roster', 'batch': '2026-2027'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(InternAccess.objects.count(), 2)
        self.grant.refresh_from_db()
        self.assertEqual(self.grant.expires_at, original_expiry)
        self.assertEqual(AuditEvent.objects.filter(action='access_change').count(), 1)
        response = self.client.post(url, {'emails': 'invalid address', 'reason': 'Synthetic semester'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(InternAccess.objects.count(), 2)

    def test_roster_paste_formats_and_invalid_lines(self):
        from .admin import SemesterInviteForm
        for text in ('FIRST@example.test\r\nSECOND@example.test',
                     'FIRST@example.test\tSECOND@example.test',
                     'FIRST@example.test; SECOND@example.test, first@example.test'):
            form = SemesterInviteForm({'emails': text, 'reason': 'Synthetic roster', 'batch': '2026-2027'})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data['emails'], ['first@example.test', 'second@example.test'])
        self.intern.is_staff = True
        self.intern.save()
        self.intern.user_permissions.add(Permission.objects.get(codename='add_internaccess'))
        response = self.client.post(reverse('admin:users_internaccess_invite'), {
            'emails': 'Email heading\r\nvalid@example.test\r\nbroken-address', 'reason': 'Synthetic roster'})
        self.assertContains(response, 'Check line(s) 1, 3:')
        self.assertContains(response, 'No invitations have been added.')
        self.assertFalse(InternAccess.objects.filter(email='valid@example.test').exists())


    def access_admin_client(self, delete=True):
        from django.test import Client
        self.doctor.is_staff = True
        self.doctor.save()
        codes = ['view_internaccess', 'change_internaccess', 'add_internaccess']
        if delete:
            codes.append('delete_internaccess')
        self.doctor.user_permissions.add(*Permission.objects.filter(codename__in=codes))
        client = Client()
        client.force_login(self.doctor)
        return client

    def test_batch_invitation_preserves_existing_batch_and_all_access_settings(self):
        from .admin import SemesterInviteForm
        self.grant.batch = '2025-2026'
        self.grant.revoked = True
        self.grant.save()
        before = (self.grant.starts_at, self.grant.expires_at, self.grant.reason)
        admin = self.access_admin_client()
        response = admin.post(reverse('admin:users_internaccess_invite'), {
            'batch': '2027-2028', 'emails': self.grant.email + '\nnewbatch@example.test', 'reason': 'Synthetic new cohort'})
        self.assertEqual(response.status_code, 302)
        self.grant.refresh_from_db()
        self.assertEqual((self.grant.starts_at, self.grant.expires_at, self.grant.reason), before)
        self.assertTrue(self.grant.revoked)
        self.assertEqual(self.grant.batch, '2025-2026')
        self.assertEqual(InternAccess.objects.get(email='newbatch@example.test').batch, '2027-2028')
        for invalid in ['2026-2028', '2026/2027', 'bad', '']:
            form = SemesterInviteForm({'batch': invalid, 'emails': 'valid@example.test', 'reason': 'Synthetic'})
            self.assertFalse(form.is_valid())
            self.assertIn('batch', form.errors)

    def test_bulk_deletion_requires_confirmation_and_revokes_existing_session(self):
        visit = self.create_visit()
        other = InternAccess.objects.create(email='selected@example.test', reason='Synthetic selected', batch='2026-2027')
        retained = InternAccess.objects.create(email='retained@example.test', reason='Synthetic retained', batch='2027-2028')
        self.grant.batch = '2026-2027'; self.grant.save()
        admin = self.access_admin_client()
        url = reverse('admin:users_internaccess_changelist')
        page = admin.get(url)
        self.assertContains(page, 'Select all on this page')
        self.assertContains(page, 'Delete selected access')
        self.assertContains(page, 'intern_access_admin.js')
        data = {'action': 'delete_selected', '_selected_action': [self.grant.pk, other.pk], 'index': '0'}
        preview = admin.post(url, data)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Yes, I')
        self.assertEqual(InternAccess.objects.count(), 3)
        self.assertEqual(AuditEvent.objects.filter(action='access_delete').count(), 0)
        confirmed = admin.post(url, {**data, 'post': 'yes'})
        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(list(InternAccess.objects.values_list('pk', flat=True)), [retained.pk])
        self.assertEqual(AuditEvent.objects.filter(action='access_delete').count(), 2)
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.intern.pk).exists())
        self.assertTrue(Visit.objects.filter(pk=visit.pk).exists())
        self.assertEqual(Photo.objects.count(), 1)
        self.assertEqual(admin.get(reverse('visit_detail', args=[visit.pk])).status_code, 200)

    def test_select_all_filtered_batch_keeps_other_batches(self):
        self.grant.batch='2026-2027'; self.grant.save()
        InternAccess.objects.create(email='samebatch@example.test', reason='Synthetic', batch='2026-2027')
        retained = InternAccess.objects.create(email='differentbatch@example.test', reason='Synthetic', batch='2027-2028')
        admin = self.access_admin_client()
        url = reverse('admin:users_internaccess_changelist') + '?batch__exact=2026-2027'
        response = admin.post(url, {'action': 'delete_selected', '_selected_action': [self.grant.pk],
            'select_across': '1', 'post': 'yes', 'index': '0'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(InternAccess.objects.values_list('pk', flat=True)), [retained.pk])
        self.assertEqual(AuditEvent.objects.filter(action='access_delete').count(), 2)

    def test_single_delete_and_staff_without_delete_permission(self):
        admin = self.access_admin_client(delete=False)
        url = reverse('admin:users_internaccess_delete', args=[self.grant.pk])
        self.assertEqual(admin.post(url, {'post': 'yes'}).status_code, 403)
        self.assertTrue(InternAccess.objects.filter(pk=self.grant.pk).exists())
        self.assertNotContains(admin.get(reverse('admin:users_internaccess_changelist')), 'access-delete-selected')
        self.doctor.user_permissions.add(Permission.objects.get(codename='delete_internaccess'))
        self.assertEqual(admin.get(url).status_code, 200)
        self.assertTrue(InternAccess.objects.filter(pk=self.grant.pk).exists())
        self.assertEqual(admin.post(url, {'post': 'yes'}).status_code, 302)
        self.assertFalse(InternAccess.objects.filter(pk=self.grant.pk).exists())
        self.assertEqual(self.client.get(reverse('submit_patient_details')).status_code, 403)
        self.assertEqual(AuditEvent.objects.filter(action='access_delete').count(), 1)

    def test_grant_deletion_rolls_back_if_audit_fails(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().post('/')
        request.user = self.doctor
        with patch('users.admin.AuditEvent.objects.create', side_effect=RuntimeError('Synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                admin.site._registry[InternAccess].delete_queryset(request, InternAccess.objects.all())
        self.assertTrue(InternAccess.objects.filter(pk=self.grant.pk).exists())

    def test_six_digit_case_numbers_optional_shift_and_previous_case(self):
        from .forms import PatientDetailsForm, DoctorSearchForm
        form = PatientDetailsForm(submission(patient_id='2413', previous_opd_number='99'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['patient_id'], '002413')
        self.assertEqual(form.cleaned_data['previous_opd_number'], '000099')
        self.assertFalse(form.cleaned_data['tf_shift'])
        for value in ['1000000', '000000', '0', 'ABC', '24/13']:
            form = PatientDetailsForm(submission(patient_id=value))
            self.assertFalse(form.is_valid())
            self.assertIn('patient_id', form.errors)
        form = DoctorSearchForm({'patient_id': '2413'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['patient_id'], '002413')
        first = self.create_visit(patient_id='2413')
        again = self.create_visit(patient_id='002413')
        self.assertEqual(first.patient_id, again.patient_id)
        self.assertEqual([first.visit_number, again.visit_number], [1, 2])

    @override_settings(PHOTO_STORAGE='drive')
    def test_location_folder_names_use_first_visit_and_retry_is_stable(self):
        from .models import photo_path
        from .case_numbers import ANAND, TF
        # Path generation is exercised with private filesystem bytes; Drive calls are mocked elsewhere.
        with override_settings(PHOTO_STORAGE='filesystem'):
            first = self.create_visit(patient_id='2413', name_of_patient='Synthetic Patient Name',
                diagnosis='First Visit Reason', name_of_intern='Synthetic Intern Name')
            second = self.create_visit(patient_id='2413', name_of_patient='Changed Patient Name',
                diagnosis='Follow Up Reason', name_of_intern='Another Intern Name')
            other = self.create_visit(patient_id='2413', tf_shift=True)
        self.assertEqual(first.patient_folder_name, '002413_Synthetic-Patient-Name_First-Visit-Reason')
        self.assertEqual(second.patient_folder_name, first.patient_folder_name)
        self.assertEqual(first.patient.location, ANAND)
        self.assertEqual(other.patient.location, TF)
        self.assertNotEqual(first.patient_id, other.patient_id)
        self.assertEqual(other.visit_number, 1)
        self.assertTrue(photo_path(second.photos.get(), 'ignored').startswith(
            'AnandHospital/002413_Synthetic-Patient-Name_First-Visit-Reason/2_Follow-Up-Reason_Another-Intern-Name/'))
        self.assertTrue(photo_path(other.photos.get(), 'ignored').startswith('TribhuvandasFoundation/002413_'))
        self.client.force_login(self.doctor)
        result = self.client.post(reverse('doctor_search'), {'patient_id': '2413'})
        self.assertEqual(len(result.context['patient_groups']), 2)
        self.assertContains(result, 'Tribhuvandas Foundation')
        result = self.client.post(reverse('doctor_search'), {'patient_id': '2413', 'location': TF})
        self.assertEqual(len(result.context['visits']), 1)
        result = self.client.post(reverse('comparison'), {'patient_id': '2413', 'location': TF,
            'photos': [str(first.photos.get().pk), str(second.photos.get().pk)]})
        self.assertEqual(result.context['patient'].pk, other.patient_id)
        self.assertEqual(result.context['selected'], [])
        self.assertEqual(len(result.context['photos']), 1)

    def test_retry_cannot_switch_location(self):
        data = submission()
        photos = compress_photos([synthetic_photo()])
        first = save_submission(self.intern, data, photos)
        with self.assertRaises(ValidationError):
            save_submission(self.intern, {**data, 'tf_shift': True}, photos)
        repeated = save_submission(self.intern, data, photos)
        self.assertEqual(repeated.pk, first.pk)
        self.assertEqual(repeated.visit_number, 1)
        self.assertEqual(Visit.objects.count(), 1)

    def test_folder_punctuation_is_not_a_path_or_query(self):
        from .case_numbers import folder_words
        self.assertEqual(folder_words('  Synthetic   Multi Word  '), 'Synthetic-Multi-Word')
        self.assertEqual(folder_words("../Unsafe / Folder's name"), 'Unsafe-Folder-s-name')
        self.assertEqual(folder_words('word ' * 30), '-'.join(['word'] * 30))
        with self.assertRaises(ValidationError):
            folder_words('a' * 1000)


    def test_drive_storage_routes_only_to_selected_location_and_validates_paths(self):
        from django.core.files.base import ContentFile
        from .drive_storage import PrivateDriveStorage, DriveStorageError
        from .case_numbers import TF
        storage = PrivateDriveStorage('synthetic.json', 'root', {TF: 'tf_folder'})
        path = TF + '/002413_Synthetic-Patient_First-Reason/1_First-Reason_Synthetic-Intern/' + 'a' * 32 + '.jpg'
        with patch('users.drive_storage.authorized_session'), \
                patch.object(storage, '_folder', return_value='nested_folder') as folder, \
                patch.object(storage, '_create', return_value='synthetic_file'):
            self.assertEqual(storage._save(path, ContentFile(b'synthetic')), 'drive/synthetic_file')
            self.assertEqual(folder.call_args_list[0].args[1:], ('tf_folder', '002413_Synthetic-Patient_First-Reason'))
            self.assertEqual(folder.call_args_list[1].args[1:], ('nested_folder', '1_First-Reason_Synthetic-Intern'))
            self.assertEqual(folder.call_count, 2)
        for unsafe in ('../' + path, path.replace('TribhuvandasFoundation', 'OtherLocation'),
                       path.replace('1_First', '0_First'), path.replace('Synthetic-Patient', "Unsafe'Name")):
            with patch('users.drive_storage.authorized_session') as session:
                with self.assertRaises(DriveStorageError):
                    storage._save(unsafe, ContentFile(b'synthetic'))
                session.assert_not_called()

    def test_legacy_case_normalization_migration_and_collision_guard(self):
        import importlib
        from django.apps import apps
        from types import SimpleNamespace
        migration = importlib.import_module('users.migrations.0003_patient_location_visit_patient_folder_name_and_more')
        patient = Patient.objects.create(patient_id='45')
        first = Visit.objects.create(patient=patient, submitted_by=self.intern, consent_confirmed=True,
            opd_number='', case_year='2026', details={})
        second = Visit.objects.create(patient=patient, submitted_by=self.intern, consent_confirmed=True,
            opd_number='', case_year='2026', details={})
        migration.normalize_existing_records(apps, SimpleNamespace(connection=connection))
        patient.refresh_from_db(); first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(patient.patient_id, '000045')
        self.assertEqual([first.visit_number, second.visit_number], [1, 2])
        Patient.objects.create(patient_id='45')
        with self.assertRaisesRegex(RuntimeError, 'normalization conflict'):
            migration.normalize_existing_records(apps, SimpleNamespace(connection=connection))
        self.assertTrue(Patient.objects.filter(patient_id='45').exists())


@skipUnless(connection.vendor == 'postgresql', 'Concurrent quota verification requires PostgreSQL; covered in CI.')
class ConcurrentQuotaTests(TransactionTestCase):
    def test_two_concurrent_uploads_cannot_exceed_quota(self):
        user = get_user_model().objects.create_user('concurrent', email='concurrent@example.test')
        EmailAddress.objects.create(user=user, email=user.email, verified=True)
        InternAccess.objects.create(email=user.email, reason='Synthetic concurrency test')
        Patient.objects.create(patient_id='000001')
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


    def test_concurrent_followups_get_distinct_sequential_numbers(self):
        user = get_user_model().objects.create_user('sequence', email='sequence@example.test')
        EmailAddress.objects.create(user=user, email=user.email, verified=True)
        InternAccess.objects.create(email=user.email, reason='Synthetic sequence test')
        blob = compress_photos([synthetic_photo()])[0]
        barrier = Barrier(2)
        def upload():
            try:
                worker = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return save_submission(worker, submission(), [blob]).visit_number
            finally:
                connections.close_all()
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media,
                STORAGES={'default': {'BACKEND': 'users.storage.PrivateFileStorage'}}):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: upload(), range(2)))
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 2)
