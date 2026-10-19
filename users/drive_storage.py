"""Private My Drive storage using the clinic user's OAuth credentials."""
import json
import re
import uuid
from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import File
from django.core.files.storage import Storage
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API = 'https://www.googleapis.com/drive/v3/files'
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'openid',
    'https://www.googleapis.com/auth/userinfo.email']


class DriveStorageError(OSError):
    pass


def authorized_session(credentials_file):
    try:
        credentials = Credentials.from_authorized_user_file(credentials_file)
    except Exception:
        raise DriveStorageError('Storage credentials are unavailable; contact an administrator.') from None
    if credentials.token_uri != 'https://oauth2.googleapis.com/token':
        raise DriveStorageError('Unexpected OAuth token endpoint.')
    session = AuthorizedSession(credentials)
    # Retry read-only operations; writes have explicit IDs and cleanup instead.
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=.5,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=['GET', 'DELETE'])))
    return session


class PrivateDriveStorage(Storage):
    def __init__(self, credentials_file, root_folder_id, location_folder_ids=None):
        self.credentials_file = credentials_file
        self.root_folder_id = self._id(root_folder_id)
        self.location_folder_ids = {name: self._id(value) for name, value in (location_folder_ids or {}).items() if value}

    @staticmethod
    def _id(value):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value or ''):
            raise DriveStorageError('Invalid Drive reference.')
        return value

    def _request(self, session, method, url, **kwargs):
        try:
            response = session.request(method, url, timeout=(10, 60), **kwargs)
            if not response.ok:
                response.close()
                raise DriveStorageError('Private photo storage request failed; contact an administrator.')
            return response
        except DriveStorageError:
            raise
        except Exception:
            # Google responses and URLs can contain credential or record data.
            raise DriveStorageError('Private photo storage is unavailable; retry later.') from None

    def _create(self, session, metadata, data=None):
        with self._request(session, 'GET', API + '/generateIds', params={'count': 1, 'space': 'drive'}) as response:
            file_id = self._id(response.json()['ids'][0])
        metadata = {**metadata, 'id': file_id, 'appProperties': {'clinical_records': 'v1'}}
        try:
            if data is None:
                response = self._request(session, 'POST', API, json=metadata, params={'fields': 'id'})
            else:
                boundary = uuid.uuid4().hex
                body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()
                    + json.dumps(metadata).encode() + f'\r\n--{boundary}\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                    + data + f'\r\n--{boundary}--\r\n'.encode())
                response = self._request(session, 'POST', 'https://www.googleapis.com/upload/drive/v3/files',
                    params={'uploadType': 'multipart', 'fields': 'id'}, data=body,
                    headers={'Content-Type': f'multipart/related; boundary={boundary}'})
            with response:
                if response.json().get('id') != file_id:
                    raise DriveStorageError('Unexpected storage response.')
            return file_id
        except Exception:
            # A timed-out create may already have succeeded remotely.
            try:
                with session.delete(API + '/' + file_id, timeout=(10, 30)) as cleanup:
                    if cleanup.status_code not in (204, 404):
                        raise DriveStorageError('Storage cleanup requires administrator review.')
            except Exception:
                raise DriveStorageError('Storage write failed; reconciliation may be required.') from None
            raise DriveStorageError('Storage write failed; please retry.') from None

    def _folder(self, session, parent, name):
        if len(name) > 500 or not re.fullmatch(r'[\w-]+', name, flags=re.UNICODE):
            raise DriveStorageError('Unsafe storage folder name.')
        query = f"'{parent}' in parents and name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        with self._request(session, 'GET', API, params={'q': query, 'fields': 'files(id)', 'pageSize': 2}) as response:
            matches = response.json()['files']
        if len(matches) > 1:
            raise DriveStorageError('Duplicate storage folders require administrator review.')
        return self._id(matches[0]['id']) if matches else self._create(session,
            {'name': name, 'parents': [parent], 'mimeType': 'application/vnd.google-apps.folder'})

    def _save(self, name, content):
        parts = PurePosixPath(name.replace('\\', '/')).parts
        legacy = (len(parts) == 3 and re.fullmatch(r'patient_[a-f0-9]{32}', parts[0])
            and re.fullmatch(r'visit_[a-f0-9]{32}', parts[1]))
        located = (len(parts) == 4 and parts[0] in ('AnandHospital', 'TribhuvandasFoundation')
            and re.fullmatch(r'[0-9]{6}_[\w-]+_[\w-]+', parts[1])
            and re.fullmatch(r'[1-9][0-9]*_[\w-]+_[\w-]+', parts[2])
            and all(len(part) <= 500 for part in parts[:-1]))
        if not (legacy or located) or not re.fullmatch(r'[a-f0-9]{32}\.jpg', parts[-1]):
            raise DriveStorageError('Invalid private photo path.')
        from django.conf import settings
        data = content.read(settings.MAX_IMAGE_BYTES + 1)
        if len(data) > settings.MAX_IMAGE_BYTES:
            raise DriveStorageError('Compressed photograph exceeds storage bounds.')
        with authorized_session(self.credentials_file) as session:
            parent = self.root_folder_id
            folders = parts[:-1]
            if located and self.location_folder_ids.get(parts[0]):
                parent = self.location_folder_ids[parts[0]]
                folders = parts[1:-1]
            for folder in folders:
                parent = self._folder(session, parent, folder)
            file_id = self._create(session, {'name': parts[-1], 'parents': [parent], 'mimeType': 'image/jpeg'}, data)
        return 'drive/' + file_id

    def _reference(self, name):
        if not name.startswith('drive/'):
            raise DriveStorageError('Legacy photos require explicit migration before changing storage.')
        return self._id(name[6:])

    def _metadata(self, session, name):
        with self._request(session, 'GET', API + '/' + self._reference(name),
                params={'fields': 'appProperties,mimeType,size,trashed'}) as response:
            metadata = response.json()
        if metadata.get('appProperties', {}).get('clinical_records') != 'v1' or metadata.get('trashed') or metadata.get('mimeType') != 'image/jpeg':
            raise DriveStorageError('Invalid clinical photo reference.')
        return metadata

    def _open(self, name, mode='rb'):
        if mode != 'rb':
            raise DriveStorageError('Private photographs are read-only.')
        from django.conf import settings
        with authorized_session(self.credentials_file) as session:
            metadata = self._metadata(session, name)
            if int(metadata['size']) > settings.MAX_IMAGE_BYTES:
                raise DriveStorageError('Stored photograph exceeds download bounds.')
            with self._request(session, 'GET', API + '/' + self._reference(name), params={'alt': 'media'}, stream=True) as response:
                output = BytesIO()
                for chunk in response.iter_content(64 * 1024):
                    if output.tell() + len(chunk) > settings.MAX_IMAGE_BYTES:
                        raise DriveStorageError('Stored photograph exceeds download bounds.')
                    output.write(chunk)
                output.seek(0)
                return File(output, name=name)

    def delete(self, name):
        with authorized_session(self.credentials_file) as session:
            self._metadata(session, name)
            with self._request(session, 'DELETE', API + '/' + self._reference(name)):
                pass

    def exists(self, name):
        # Writes always receive fresh UUID paths; never overwrite existing files.
        return False

    def get_available_name(self, name, max_length=None):
        # Input paths organize folders; only the short returned drive/<id> is
        # stored in FileField. Do not truncate the temporary UUID filename.
        return name

    def url(self, name):
        raise ValueError('Clinical photographs must use the authorized photo route.')
