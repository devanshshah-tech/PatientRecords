"""Prepare app-owned location folders without requesting broader Drive scopes."""
from pathlib import Path
import os
from dotenv import set_key
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from users.case_numbers import ANAND, TF
from users.drive_storage import API, authorized_session, PrivateDriveStorage


class Command(BaseCommand):
    help = 'Prepare private location folders and store their IDs in an ignored environment file.'

    def add_arguments(self, parser):
        parser.add_argument('--env-file', default=str(settings.BASE_DIR / '.env.local'))

    def handle(self, *args, **options):
        credentials = os.getenv('DRIVE_CREDENTIALS_FILE')
        root = os.getenv('DRIVE_ROOT_FOLDER_ID')
        if not credentials or not root:
            raise CommandError('Configure Drive authorization first.')
        target = Path(options['env_file']).resolve()
        # Never create a tracked configuration file containing storage references.
        if target.name not in ('.env', '.env.local', 'render-preview.env'):
            raise CommandError('Use an ignored environment file.')
        try:
            storage = PrivateDriveStorage(credentials, root)
            with authorized_session(credentials) as session:
                with storage._request(session, 'GET', API + '/' + storage.root_folder_id,
                        params={'fields': 'mimeType,trashed,permissions(type,role)'}) as response:
                    metadata = response.json()
                if (metadata.get('trashed') or metadata.get('mimeType') != 'application/vnd.google-apps.folder'
                        or any(p.get('type') != 'user' or p.get('role') != 'owner' for p in metadata.get('permissions', []))):
                    raise CommandError('Storage root must be an unshared private folder.')
                folders = {key: storage._folder(session, root, name) for name, key in
                    ((ANAND, 'DRIVE_ANAND_FOLDER_ID'), (TF, 'DRIVE_TF_FOLDER_ID'))}
            for key, value in folders.items():
                set_key(str(target), key, value)
        except CommandError:
            raise
        except Exception:
            raise CommandError('Location folder preparation failed; no storage references or credentials were logged.') from None
        self.stdout.write('PASS private AnandHospital and TribhuvandasFoundation folders prepared; IDs saved in ignored environment configuration. Existing files unchanged.')
