"""Migrate using the direct URL, then start the managed preview server."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
environment = {**os.environ, 'DJANGO_DATABASE_UNPOOLED': 'true'}
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=root, env=environment, check=True)
os.execv(sys.executable, [sys.executable, str(root / 'scripts' / 'serve.py')])
