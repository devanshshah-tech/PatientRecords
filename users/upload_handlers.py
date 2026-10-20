from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import MemoryFileUploadHandler


class BoundedMemoryUploadHandler(MemoryFileUploadHandler):
    """Bound memory while parsing multipart files, before form/view validation."""
    total_bytes = 0

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length and content_length > settings.MAX_UPLOAD_BYTES + 1024 * 1024:
            raise RequestDataTooBig('Request exceeds the upload limit.')
        self.activated = True

    def new_file(self, *args, **kwargs):
        self.current_bytes = 0
        super().new_file(*args, **kwargs)

    def receive_data_chunk(self, raw_data, start):
        self.total_bytes += len(raw_data)
        self.current_bytes += len(raw_data)
        if self.total_bytes > settings.MAX_UPLOAD_BYTES or self.current_bytes > settings.MAX_IMAGE_BYTES:
            raise RequestDataTooBig('Photograph upload exceeds the size limit.')
        return super().receive_data_chunk(raw_data, start)
