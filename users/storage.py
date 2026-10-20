from django.core.files.storage import FileSystemStorage


class PrivateFileStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError('Clinical photographs must be delivered through the authorized photo route.')
