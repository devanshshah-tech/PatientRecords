"""Synthetic write/read/delete smoke check, independent of clinical records."""
from io import BytesIO
import os
import uuid

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from users.drive_storage import PrivateDriveStorage


class Command(BaseCommand):
    help = 'Verify Drive with one synthetic JPEG; never copies clinical records.'

    def handle(self, *args, **options):
        if not os.getenv('DRIVE_CREDENTIALS_FILE') or not os.getenv('DRIVE_ROOT_FOLDER_ID'):
            raise CommandError('Run connect_drive first.')
        storage = PrivateDriveStorage(os.environ['DRIVE_CREDENTIALS_FILE'], os.environ['DRIVE_ROOT_FOLDER_ID'])
        buffer = BytesIO()
        Image.new('RGB', (32, 32), (100, 140, 160)).save(buffer, 'JPEG')
        original = buffer.getvalue()
        name = None
        try:
            marker = uuid.uuid4().hex
            name = storage.save(f'patient_{marker}/visit_{marker}/{marker}.jpg', ContentFile(original))
            with storage.open(name) as result:
                if result.read() != original:
                    raise CommandError('Drive read-back did not match the synthetic upload.')
            self.stdout.write('PASS synthetic Drive upload and exact read-back.')
        finally:
            if name:
                storage.delete(name)
                self.stdout.write('PASS synthetic Drive file deleted. Empty test folders are retained for reconciliation.')
