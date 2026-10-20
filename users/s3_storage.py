from storages.backends.s3 import S3Storage


class PrivateS3Storage(S3Storage):
    def url(self, name, **kwargs):
        raise ValueError('Clinical photographs must be delivered through the authorized photo route.')
