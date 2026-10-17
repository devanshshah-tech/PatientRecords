"""Test runner settings used only by scripts/verify_neon.py's disposable branch."""
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

if not os.getenv('NEON_VERIFICATION_BRANCH_NAME', '').startswith('agent-verify-'):
    raise ImproperlyConfigured('Live database tests require an explicitly identified disposable verification branch.')

# The orchestrator creates this branch without production rows and deletes it afterward.
# Reuse its database to avoid requiring CREATE DATABASE privileges on the managed host.
DATABASES['default']['TEST'] = {'NAME': DATABASES['default']['NAME']}  # noqa: F405
