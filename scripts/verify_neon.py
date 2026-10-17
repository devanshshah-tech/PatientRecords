"""Verify PostgreSQL and real HTTP workflows on a disposable, schema-only Neon branch."""
import argparse
from datetime import datetime, timedelta, timezone
from http.cookiejar import Cookie, CookieJar
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, Request
import uuid

from dotenv import dotenv_values
import psycopg

ROOT = Path(__file__).resolve().parent.parent
PROJECT = 'delicate-wind-71461620'


def neon(*args, json_output=False):
    executable = shutil.which('neon.cmd' if os.name == 'nt' else 'neon')
    if not executable:
        raise RuntimeError('Neon CLI is not installed.')
    result = subprocess.run([executable, *args], cwd=ROOT, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=180)
    if result.returncode:
        # Connection-string responses are sensitive: never echo subprocess payloads.
        raise RuntimeError(f'Neon {args[0]} failed with exit code {result.returncode}; no credentials were logged.')
    return json.loads(result.stdout) if json_output else result.stdout.strip()


def connection_check(url, label):
    with psycopg.connect(url, connect_timeout=20, autocommit=True, prepare_threshold=None) as database:
        assert database.pgconn.ssl_in_use, 'Database connection must use TLS.'
        with database.cursor() as cursor:
            cursor.execute('SELECT 1, current_setting(%s)', ('server_version',))
            result, version = cursor.fetchone()
            assert result == 1
    print(f'PASS {label}: SELECT 1 over TLS, PostgreSQL {version}', flush=True)


def run_python(args, environment):
    result = subprocess.run([sys.executable, *args], cwd=ROOT, env=environment)
    if result.returncode:
        raise RuntimeError(f'Python {args[0]} verification step failed ({result.returncode}).')


def http_workflow(environment):
    sys.path.insert(0, str(ROOT))
    os.environ.update(environment)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'patientrecords.settings'
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.contrib.sessions.backends.db import SessionStore
    from django.db import connection
    from allauth.account.models import EmailAddress
    from PIL import Image
    from users.models import InternAccess, Patient, Visit

    def account(username, doctor=False):
        user = get_user_model().objects.create_user(username, email=f'{username}@example.test')
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        if doctor:
            user.user_permissions.add(Permission.objects.get(codename='compare_patients'))
        else:
            InternAccess.objects.create(email=user.email, reason='Synthetic end-to-end verification')
        session = SessionStore()
        session['_auth_user_id'] = str(user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = user.get_session_auth_hash()
        session.save()
        return user, session.session_key

    intern, intern_session = account('neon_synthetic_intern')
    doctor, doctor_session = account('neon_synthetic_doctor', doctor=True)
    connection.close()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    server_environment = {**environment, 'PORT': str(port), 'BIND_HOST': '127.0.0.1'}
    creation = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    server = subprocess.Popen([sys.executable, 'scripts/serve.py'], cwd=ROOT, env=server_environment, **creation)
    base = f'http://127.0.0.1:{port}'

    def browser(session=None):
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        if session:
            jar.set_cookie(Cookie(version=0, name=settings.SESSION_COOKIE_NAME, value=session,
                port=None, port_specified=False, domain='127.0.0.1', domain_specified=False,
                domain_initial_dot=False, path='/', path_specified=True, secure=False,
                expires=None, discard=True, comment=None, comment_url=None, rest={}))
        return opener, jar

    def get(opener, path):
        with opener.open(base + path, timeout=30) as response:
            return response.status, response.read(), response.headers

    def post(opener, jar, path, values):
        csrf = next(cookie.value for cookie in jar if cookie.name == 'csrftoken')
        data = urlencode({'csrfmiddlewaretoken': csrf, **values}, doseq=True).encode()
        with opener.open(Request(base + path, data=data), timeout=30) as response:
            return response.status, response.read(), response.headers

    try:
        anonymous, _ = browser()
        for attempt in range(60):
            try:
                status, _, _ = get(anonymous, '/')
                break
            except URLError:
                if server.poll() is not None:
                    raise RuntimeError('Waitress exited before readiness.')
                time.sleep(0.5)
        else:
            raise RuntimeError('Waitress readiness timed out.')
        assert status == 200
        print('PASS running application: HTTP GET / returned 200', flush=True)
        intern_browser, jar = browser(intern_session)
        assert get(intern_browser, '/submit-patient-details/')[0] == 200
        csrf = next(cookie.value for cookie in jar if cookie.name == 'csrftoken')
        image = BytesIO()
        Image.new('RGB', (64, 64), (100, 160, 190)).save(image, 'JPEG')
        boundary = 'clinical-synthetic-' + uuid.uuid4().hex
        values = {'csrfmiddlewaretoken': csrf, 'submission_id': str(uuid.uuid4()), 'patient_id': 'NEON-SYNTHETIC-001',
            'consent_confirmed': 'on', 'opd_number': 'SYNTHETIC-OPD', 'case_year': '2026',
            'name_of_patient': 'Synthetic verification only', 'age': '25', 'gender': 'O',
            'diagnosis': 'Synthetic test condition', 'name_of_intern': 'Synthetic intern', 'roll_number': '1'}
        body = BytesIO()
        for key, value in values.items():
            body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="patient_images"; filename="synthetic.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
        body.write(image.getvalue())
        body.write(f'\r\n--{boundary}--\r\n'.encode())
        request = Request(base + '/submit-patient-details/', data=body.getvalue(),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with intern_browser.open(request, timeout=45) as response:
            assert response.status == 200
            assert b'Patient record and photographs saved securely.' in response.read()
        connection.close()
        visit = Visit.objects.get(patient__patient_id='NEON-SYNTHETIC-001')
        photo = visit.photos.get()
        assert visit.submitted_by_id == intern.pk and visit.consent_confirmed
        assert Patient.objects.get(pk=visit.patient_id).photo_bytes == photo.size_bytes
        print('PASS real HTTP upload: consented visit persisted in Neon with uploader and photo quota', flush=True)
        try:
            get(intern_browser, f'/photos/{photo.pk}/')
            raise AssertionError('Intern must not retrieve photographs.')
        except HTTPError as error:
            assert error.code == 403
        print('PASS real HTTP privacy: intern photo request returned 403', flush=True)
        doctor_browser, doctor_jar = browser(doctor_session)
        assert get(doctor_browser, '/doctor/')[0] == 200
        status, content, _ = post(doctor_browser, doctor_jar, '/doctor/', {'patient_id': 'NEON-SYNTHETIC-001'})
        assert status == 200 and b'NEON-SYNTHETIC-001' in content
        status, content, headers = get(doctor_browser, f'/photos/{photo.pk}/')
        assert status == 200 and content.startswith(b'\xff\xd8')
        assert headers['Cache-Control'] == 'no-store, private'
        print('PASS real HTTP doctor search/photo: 200, private JPEG, no-store response', flush=True)
        InternAccess.objects.filter(email=intern.email).update(revoked=True)
        connection.close()
        try:
            get(intern_browser, '/submit-patient-details/')
            raise AssertionError('Revoked intern session must fail.')
        except HTTPError as error:
            assert error.code == 403
        print('PASS real HTTP access revocation: existing session returned 403', flush=True)
    finally:
        server.terminate()
        server.wait(timeout=15)
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true', help='Skip the full regression suite; still run live SQL and HTTP smoke checks.')
    args = parser.parse_args()
    local = dotenv_values(ROOT / ('.env' if (ROOT / '.env').exists() else '.env.local'))
    connection_check(local['DATABASE_URL'], 'linked production pooled connection (read-only)')
    name = 'agent-verify-' + uuid.uuid4().hex[:12]
    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    print(f'Creating disposable schema-only branch {name}', flush=True)
    created = neon('branches', 'create', '--project-id', PROJECT, '--name', name, '--parent', 'production',
        '--schema-only', '--no-secrets', '--expires-at', expiry, '-o', 'json', json_output=True)
    branch = created.get('branch', created)
    branch_id = branch['id']
    if branch.get('name') != name or not branch_id.startswith('br-'):
        raise RuntimeError('Unexpected branch metadata; no database tests were run.')
    try:
        direct = neon('connection-string', branch_id, '--project-id', PROJECT)
        pooled = neon('connection-string', branch_id, '--project-id', PROJECT, '--pooled')
        assert urlsplit(direct).hostname != urlsplit(local['DATABASE_URL_UNPOOLED']).hostname
        connection_check(pooled, 'isolated verification pooled connection')
        with tempfile.TemporaryDirectory(prefix='clinical-neon-verify-') as media:
            environment = {**os.environ, 'DJANGO_LOAD_ENV_FILES': 'false', 'DJANGO_DEBUG': 'true',
                'DJANGO_SECRET_KEY': uuid.uuid4().hex + uuid.uuid4().hex,
                'DJANGO_ALLOWED_HOSTS': '127.0.0.1,localhost,testserver',
                'DJANGO_DATABASE_UNPOOLED': 'false', 'DATABASE_URL': direct,
                'DATABASE_URL_UNPOOLED': direct, 'PHOTO_STORAGE': 'filesystem', 'PRIVATE_MEDIA_ROOT': media,
                'NEON_VERIFICATION_BRANCH_NAME': name}
            print('Running migrations on isolated branch using direct connection', flush=True)
            run_python(['manage.py', 'migrate', '--noinput'], environment)
            if not args.skip_tests:
                print('Running full Django/PostgreSQL regressions, including concurrent quota test', flush=True)
                run_python(['manage.py', 'test', 'users', 'patientrecords.tests',
                    '--settings', 'patientrecords.neon_test_settings', '--keepdb', '--noinput'], environment)
            environment['DATABASE_URL'] = pooled
            environment['DJANGO_SETTINGS_MODULE'] = 'patientrecords.settings'
            http_workflow(environment)
        print('PASS Neon integration end to end; production rows were not copied or modified.', flush=True)
    finally:
        print(f'Removing disposable verification branch {name}', flush=True)
        neon('branches', 'delete', branch_id, '--project-id', PROJECT)
        print('Disposable verification branch removed.', flush=True)


if __name__ == '__main__':
    main()
