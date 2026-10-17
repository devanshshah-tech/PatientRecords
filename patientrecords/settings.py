import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
from .database import database_config

BASE_DIR = Path(__file__).resolve().parent.parent
if os.getenv('DJANGO_LOAD_ENV_FILES', 'true').lower() == 'true':
    # Shell/service variables win; Neon writes .env.local unless .env already exists.
    load_dotenv(BASE_DIR / '.env.local', override=False)
    load_dotenv(BASE_DIR / '.env', override=False)
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'development-only-do-not-use-in-production'
    else:
        raise ImproperlyConfigured('Set DJANGO_SECRET_KEY or enable DJANGO_DEBUG for local development.')
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [v for v in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if v]
render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME', '')
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS.append('https://' + render_hostname)
SITE_ID = 1
PREVIEW_MODE = os.getenv('PREVIEW_MODE', 'false').lower() == 'true'
CLINICAL_UPLOADS_ENABLED = os.getenv('CLINICAL_UPLOADS_ENABLED', 'true').lower() == 'true'
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'django.contrib.sites', 'users', 'allauth', 'allauth.account',
    'allauth.socialaccount', 'allauth.socialaccount.providers.google',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware', 'users.middleware.ClinicalPrivacyMiddleware',
]
ROOT_URLCONF = 'patientrecords.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': [
        'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'users.context_processors.deployment_mode',
    ]}}]
WSGI_APPLICATION = 'patientrecords.wsgi.application'
DATABASES = {'default': database_config(os.environ, BASE_DIR, DEBUG)}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.' + name} for name in
    ['UserAttributeSimilarityValidator', 'MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator']]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'users.storage.PrivateFileStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
PHOTO_STORAGE = os.getenv('PHOTO_STORAGE', 'filesystem')
if PHOTO_STORAGE == 'drive':
    STORAGES['default'] = {'BACKEND': 'users.drive_storage.PrivateDriveStorage', 'OPTIONS': {
        'credentials_file': os.environ['DRIVE_CREDENTIALS_FILE'],
        'root_folder_id': os.environ['DRIVE_ROOT_FOLDER_ID'],
    }}
elif PHOTO_STORAGE == 's3':
    STORAGES['default'] = {'BACKEND': 'users.s3_storage.PrivateS3Storage', 'OPTIONS': {
        'access_key': os.environ['S3_ACCESS_KEY_ID'],
        'secret_key': os.environ['S3_SECRET_ACCESS_KEY'],
        'bucket_name': os.environ['S3_BUCKET_NAME'],
        'endpoint_url': os.environ['S3_ENDPOINT_URL'],
        'region_name': os.getenv('S3_REGION_NAME', 'us-east-1'),
        'addressing_style': 'path', 'signature_version': 's3v4',
        'default_acl': None, 'file_overwrite': False, 'querystring_auth': True,
        'object_parameters': {'CacheControl': 'no-store'},
    }}
MEDIA_ROOT = Path(os.getenv('PRIVATE_MEDIA_ROOT') or str(BASE_DIR / 'private-media'))
if PHOTO_STORAGE not in ('filesystem', 's3', 'drive'):
    raise ImproperlyConfigured('Unsupported PHOTO_STORAGE setting.')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend', 'allauth.account.auth_backends.AuthenticationBackend']
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/accounts/google/login/'
# Google verification is enforced by the adapter and on every clinical request.
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_ADAPTER = 'users.adapters.ClosedAccountAdapter'
ACCOUNT_USER_DISPLAY = 'users.identity.user_display'
SOCIALACCOUNT_ADAPTER = 'users.adapters.InvitedSocialAdapter'
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_PROVIDERS = {'google': {'APP': {
    'client_id': os.getenv('SOCIAL_AUTH_GOOGLE_CLIENT_ID', ''),
    'secret': os.getenv('SOCIAL_AUTH_GOOGLE_SECRET', ''), 'key': ''},
    'SCOPE': ['profile', 'email'], 'AUTH_PARAMS': {'access_type': 'online', 'prompt': 'select_account'}}}
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
# Preserve same-origin form origins for CSRF without leaking URLs externally.
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
if os.getenv('TRUST_HTTPS_PROXY', 'false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PHOTOS_PER_VISIT = 10
PATIENT_PHOTO_QUOTA_BYTES = 50 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_IMAGE_BYTES
DATA_UPLOAD_MAX_NUMBER_FILES = MAX_PHOTOS_PER_VISIT
FILE_UPLOAD_HANDLERS = ['users.upload_handlers.BoundedMemoryUploadHandler']
