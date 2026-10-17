"""One-time operator OAuth setup; never part of intern/doctor sign-in."""
import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession

from users.drive_storage import PrivateDriveStorage, SCOPES


class Command(BaseCommand):
    help = 'Authorize a clinic-owned My Drive and create a private app folder. Does not enable Drive storage.'

    def add_arguments(self, parser):
        parser.add_argument('--expected-email', required=True)

    def handle(self, *args, **options):
        directory = settings.BASE_DIR / '.secrets'
        client_file = directory / 'drive-client.json'
        token_file = directory / 'drive-token.json'
        if token_file.exists():
            raise CommandError('Drive credentials already exist; explicit reconnection/rotation is required.')
        if not client_file.exists():
            raise CommandError('Save the separate Desktop OAuth client JSON as .secrets/drive-client.json first.')
        config = json.loads(client_file.read_text(encoding='utf-8-sig'))
        client = config.get('installed', {})
        if client.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth' or client.get('token_uri') != 'https://oauth2.googleapis.com/token':
            raise CommandError('Expected a Google Desktop OAuth client JSON.')
        try:
            flow = InstalledAppFlow.from_client_config(config, SCOPES, autogenerate_code_verifier=True)
            credentials = flow.run_local_server(host='127.0.0.1', port=0, timeout_seconds=300,
                prompt='consent select_account', access_type='offline',
                authorization_prompt_message='Finish storage authorization in the browser window.',
                success_message='Authorization received. You may close this tab and return to the terminal.')
            if not credentials.refresh_token:
                raise CommandError('No offline refresh token received; reconnect with consent.')
            with AuthorizedSession(credentials) as session:
                response = session.get('https://openidconnect.googleapis.com/v1/userinfo', timeout=30)
                response.raise_for_status()
                identity = response.json()
                if not identity.get('email_verified') or identity.get('email', '').lower() != options['expected_email'].strip().lower():
                    raise CommandError('Selected Google account does not match the expected verified storage owner.')
                storage = PrivateDriveStorage(str(token_file), 'temporary')
                root = storage._create(session, {'name': 'Clinical Records',
                    'mimeType': 'application/vnd.google-apps.folder'})
            directory.mkdir(mode=0o700, exist_ok=True)
            descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                output.write(credentials.to_json())
            env_file = settings.BASE_DIR / '.env.local'
            set_key(str(env_file), 'DRIVE_CREDENTIALS_FILE', str(token_file))
            set_key(str(env_file), 'DRIVE_ROOT_FOLDER_ID', root)
        except CommandError:
            raise
        except Exception:
            raise CommandError('Drive authorization/setup failed. No credentials were printed; check API access and OAuth configuration.') from None
        self.stdout.write(self.style.SUCCESS('Storage owner verified; private app folder created; credentials saved in ignored .secrets. PHOTO_STORAGE was not changed. Run verify_drive next.'))
