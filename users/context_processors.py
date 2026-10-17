from django.conf import settings


def deployment_mode(request):
    return {'preview_mode': settings.PREVIEW_MODE, 'uploads_enabled': settings.CLINICAL_UPLOADS_ENABLED}
