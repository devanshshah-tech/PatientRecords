"""Start Django with Waitress locally or on a managed Python host."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patientrecords.wsgi import application
from waitress import serve

if __name__ == '__main__':
    host = os.getenv('BIND_HOST', '127.0.0.1')
    port = int(os.getenv('PORT', '8000'))
    print(f'Starting Django/Waitress on {host}:{port}', flush=True)
    proxy = {}
    if os.getenv('TRUST_HTTPS_PROXY', 'false').lower() == 'true':
        # Use only behind the managed host's sanitizing reverse proxy.
        proxy = {'trusted_proxy': '*', 'trusted_proxy_count': 1,
            'trusted_proxy_headers': {'x-forwarded-proto'}}
    serve(application, host=host, port=port, threads=int(os.getenv('WEB_THREADS', '4')),
        max_request_body_size=27262976, clear_untrusted_proxy_headers=True, **proxy)
