"""Database settings shared by local Django and a normal hosted Python runtime."""
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


def database_config(environment, base_dir, debug):
    direct = environment.get('DJANGO_DATABASE_UNPOOLED', '').lower() == 'true'
    url = environment.get('DATABASE_URL_UNPOOLED' if direct else 'DATABASE_URL', '')
    if direct and not url:
        raise ImproperlyConfigured('Direct database operations require DATABASE_URL_UNPOOLED.')
    if url:
        try:
            config = dj_database_url.parse(url, conn_max_age=0, conn_health_checks=True)
            if config['ENGINE'] != 'django.db.backends.postgresql' or not config.get('HOST') or not config.get('NAME'):
                raise ValueError
            options = config.setdefault('OPTIONS', {})
            if options.get('sslmode', 'require') not in ('require', 'verify-ca', 'verify-full'):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ImproperlyConfigured('DATABASE_URL must be a valid PostgreSQL URL with TLS required.') from None
        options.setdefault('sslmode', 'require')
        options.setdefault('connect_timeout', 15)
        # Compatible with transaction poolers; no session-bound cursors/prepared statements.
        options['prepare_threshold'] = None
        config['DISABLE_SERVER_SIDE_CURSORS'] = True
        return config
    if environment.get('DB_NAME'):
        return {'ENGINE': 'django.db.backends.postgresql', 'NAME': environment['DB_NAME'],
            'USER': environment['DB_USER'], 'PASSWORD': environment['DB_PASSWORD'],
            'HOST': environment.get('DB_HOST', '127.0.0.1'), 'PORT': environment.get('DB_PORT', '5432')}
    if debug:
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': Path(base_dir) / 'db.sqlite3'}
    raise ImproperlyConfigured('Production requires DATABASE_URL or PostgreSQL DB_NAME, DB_USER and DB_PASSWORD.')
