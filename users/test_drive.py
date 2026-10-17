from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings
from django.core.exceptions import SuspiciousFileOperation

from .drive_storage import PrivateDriveStorage, DriveStorageError


@override_settings(MAX_IMAGE_BYTES=1024)
class DriveStorageTests(SimpleTestCase):
    def setUp(self):
        self.storage = PrivateDriveStorage('synthetic-not-a-credential.json', 'synthetic_root')

    def test_uuid_folder_path_becomes_opaque_file_reference_without_truncation(self):
        path = 'patient_' + 'a' * 32 + '/visit_' + 'b' * 32 + '/' + 'c' * 32 + '.jpg'
        with patch('users.drive_storage.authorized_session') as session, \
                patch.object(self.storage, '_folder', side_effect=['patient_folder', 'visit_folder']) as folder, \
                patch.object(self.storage, '_create', return_value='synthetic_file') as create:
            self.assertEqual(self.storage.save(path, ContentFile(b'jpeg'), max_length=100), 'drive/synthetic_file')
            self.assertEqual(folder.call_count, 2)
            self.assertEqual(create.call_args.args[1]['parents'], ['visit_folder'])
            self.assertEqual(create.call_args.args[2], b'jpeg')

    def test_invalid_paths_and_large_writes_are_rejected_before_network(self):
        with patch('users.drive_storage.authorized_session') as session:
            for name in ('../../private', 'photos/legacy.jpg', 'drive/file'):
                with self.assertRaises((DriveStorageError, SuspiciousFileOperation)):
                    self.storage.save(name, ContentFile(b'jpeg'))
            path = 'patient_' + 'a' * 32 + '/visit_' + 'b' * 32 + '/' + 'c' * 32 + '.jpg'
            with self.assertRaises(DriveStorageError):
                self.storage.save(path, ContentFile(b'x' * 1025))
            session.assert_not_called()

    def test_bounded_private_download_and_no_public_url(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b'jpeg']
        with patch('users.drive_storage.authorized_session'), \
                patch.object(self.storage, '_metadata', return_value={'size': '4'}), \
                patch.object(self.storage, '_request', return_value=response):
            with self.storage.open('drive/synthetic_file') as result:
                self.assertEqual(result.read(), b'jpeg')
            response.iter_content.return_value = [b'x' * 1025]
            with self.assertRaises(DriveStorageError):
                self.storage.open('drive/synthetic_file')
        with self.assertRaises(ValueError):
            self.storage.url('drive/synthetic_file')

    def test_ambiguous_failed_upload_attempts_cleanup_of_preallocated_id(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {'ids': ['preallocated']}
        session = MagicMock()
        session.delete.return_value.__enter__.return_value.status_code = 204
        with patch.object(self.storage, '_request', side_effect=[response, DriveStorageError('synthetic')]):
            with self.assertRaises(DriveStorageError):
                self.storage._create(session, {'name': 'synthetic.jpg'}, b'jpeg')
        self.assertTrue(session.delete.call_args.args[0].endswith('/preallocated'))

    def test_unmarked_or_legacy_references_cannot_be_deleted(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {'mimeType': 'image/jpeg', 'size': '4'}
        with patch('users.drive_storage.authorized_session') as session, \
                patch.object(self.storage, '_request', return_value=response):
            with self.assertRaises(DriveStorageError):
                self.storage.delete('drive/unmarked')
            with self.assertRaises(DriveStorageError):
                self.storage._reference('photos/legacy.jpg')
