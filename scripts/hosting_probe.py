"""Small hosting capability/short-lived process probe; no credentials or network use."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import uuid


def inspect_runtime():
    packages = {}
    for name in ('Django', 'waitress', 'mysqlclient', 'psycopg'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    disk = shutil.disk_usage(Path.cwd())
    return {'python_version': platform.python_version(), 'python_executable': sys.executable,
        'operating_system': platform.platform(), 'visible_cpu_count': os.cpu_count(),
        'physical_volume_free_gib': round(disk.free / 1024 ** 3, 2), 'packages': packages,
        'note': 'Visible CPU/disk are host information, not your subscription allocation. No environment variables are inspected.'}


def heartbeat(directory, seconds):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'heartbeat-{uuid.uuid4().hex}.jsonl'
    deadline = time.monotonic() + seconds
    print(f'Probe output: {destination}', flush=True)
    with destination.open('x', encoding='utf-8') as output:
        while True:
            finished = time.monotonic() >= deadline
            output.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(),
                'pid': os.getpid(), 'phase': 'finished' if finished else 'running'}) + '\n')
            output.flush()
            if finished:
                break
            time.sleep(min(10, max(0, deadline - time.monotonic())))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heartbeat-directory', help='Private writable directory outside httpdocs; enables a bounded heartbeat probe.')
    parser.add_argument('--heartbeat-seconds', type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.heartbeat_seconds <= 600:
        parser.error('Heartbeat duration must be between 1 and 600 seconds.')
    print(json.dumps(inspect_runtime(), indent=2), flush=True)
    if args.heartbeat_directory:
        heartbeat(args.heartbeat_directory, args.heartbeat_seconds)


if __name__ == '__main__':
    main()
