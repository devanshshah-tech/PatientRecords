from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .database import database_config

from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import path


def csrf_probe(request):
    get_token(request)
    return HttpResponse(render_to_string('base_entrance.html', request=request))


urlpatterns = [path('csrf-probe/', csrf_probe, name='index'),
    path('privacy/', lambda request: HttpResponse('Privacy policy'), name='privacy_policy')]


@override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=['testserver'],
    SECURE_SSL_REDIRECT=False, CSRF_COOKIE_SECURE=False,
    STORAGES={'default': {'BACKEND': 'users.storage.PrivateFileStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
    MIDDLEWARE=['django.middleware.security.SecurityMiddleware', 'django.middleware.csrf.CsrfViewMiddleware'])
class FormOriginTests(SimpleTestCase):
    def setUp(self):
        self.browser = Client(enforce_csrf_checks=True)
        self.page = self.browser.get('/csrf-probe/')
        self.token = self.browser.cookies['csrftoken'].value

    def test_header_and_html_preserve_same_origin_without_external_referrers(self):
        self.assertEqual(self.page.headers['Referrer-Policy'], 'same-origin')
        self.assertContains(self.page, '<meta name="referrer" content="same-origin">')

    def test_same_origin_post_passes_http_and_https(self):
        for secure in (False, True):
            origin = ('https' if secure else 'http') + '://testserver'
            response = self.browser.post('/csrf-probe/', {'csrfmiddlewaretoken': self.token},
                secure=secure, HTTP_ORIGIN=origin)
            self.assertEqual(response.status_code, 200)
        response = self.browser.post('/csrf-probe/', {'csrfmiddlewaretoken': self.token},
            secure=True, HTTP_REFERER='https://testserver/csrf-probe/')
        self.assertEqual(response.status_code, 200)

    def test_null_external_and_missing_token_posts_still_fail(self):
        for origin in ('null', 'https://untrusted.example.test'):
            response = self.browser.post('/csrf-probe/', {'csrfmiddlewaretoken': self.token}, HTTP_ORIGIN=origin)
            self.assertEqual(response.status_code, 403)
        response = self.browser.post('/csrf-probe/', HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 403)


class DatabaseSettingsTests(SimpleTestCase):
    def test_neon_url_preserves_tls_and_decodes_credentials(self):
        config = database_config({'DATABASE_URL': 'postgresql://synthetic:pass%40word@unit-pooler.example.test/neondb?sslmode=require&channel_binding=require'}, '.', False)
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['PASSWORD'], 'pass@word')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['OPTIONS']['channel_binding'], 'require')
        self.assertIsNone(config['OPTIONS']['prepare_threshold'])
        self.assertEqual(config['CONN_MAX_AGE'], 0)
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])

    def test_url_wins_over_legacy_database_settings(self):
        config = database_config({'DATABASE_URL': 'postgres://u:p@synthetic.example.test/new', 'DB_NAME': 'old'}, '.', True)
        self.assertEqual(config['NAME'], 'new')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')

    def test_direct_url_for_migrations(self):
        config = database_config({'DATABASE_URL': 'postgres://u:p@pooler.example.test/db',
            'DATABASE_URL_UNPOOLED': 'postgres://u:p@direct.example.test/db', 'DJANGO_DATABASE_UNPOOLED': 'true'}, '.', False)
        self.assertEqual(config['HOST'], 'direct.example.test')

    def test_missing_direct_url_fails(self):
        with self.assertRaises(ImproperlyConfigured):
            database_config({'DJANGO_DATABASE_UNPOOLED': 'true'}, '.', True)

    def test_invalid_or_unencrypted_urls_fail_without_echoing_them(self):
        for url in ('postgres://u:synthetic-secret@host/db?sslmode=disable', 'sqlite:///test.db', 'bad-url'):
            with self.subTest(url=url):
                with self.assertRaises(ImproperlyConfigured) as error:
                    database_config({'DATABASE_URL': url}, '.', False)
                self.assertNotIn('synthetic-secret', str(error.exception))

    def test_legacy_settings_remain_compatible(self):
        config = database_config({'DB_NAME': 'ci', 'DB_USER': 'ci', 'DB_PASSWORD': 'synthetic'}, '.', False)
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['HOST'], '127.0.0.1')

    def test_sqlite_only_when_debug_is_explicit(self):
        self.assertEqual(database_config({}, '.', True)['NAME'], Path('db.sqlite3'))
        with self.assertRaises(ImproperlyConfigured):
            database_config({}, '.', False)
