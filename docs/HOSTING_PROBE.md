# Plesk runtime experiment

This experiment is authorized for diagnosis, not a live clinical deployment. No remote commands have been executed by the coding agent: terminal access/session credentials have not been established.

Plesk offers a [PowerShell Terminal extension](https://www.plesk.com/extensions/ps-terminal/) for Windows administrators and subscription owners. Check for its availability in your Plesk interface. If absent, scheduler permissions allow investigating a one-off command task, but do not establish support for a persistent application service.

## First: inspect the terminal

Run in the Plesk terminal, not on your laptop:

```powershell
$PSVersionTable.PSVersion
Get-Location
Get-Command python, py, node -ErrorAction SilentlyContinue | Select-Object Name, Source
```

If Python is present, run `python --version` and `python -m pip --version`. If only the Python launcher is present, try `py --version` instead. Share results without credentials. Do not dump environment variables or configuration files.

Upload `scripts/hosting_probe.py` as `hosting_probe.py` to the subscription's private home directory, outside `httpdocs`. Change to that directory, then run:

```powershell
python hosting_probe.py
```

This reports Python/OS, installed relevant packages, visible CPU count and physical disk free space. Physical disk free space does not override the subscription's 2 GB quota. The probe does not install software, bind a port, read credentials or alter the application.

## Second: bounded process survival check

Only if Python works, from the same private directory:

```powershell
Start-Process -FilePath (Get-Command python).Source -ArgumentList @('hosting_probe.py', '--heartbeat-directory', 'private-probes', '--heartbeat-seconds', '300') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru
```

The child process writes a tiny heartbeat under `private-probes` every 10 seconds and exits automatically after five minutes. Close the terminal after about 30 seconds, reopen it after five minutes, then use Plesk File Manager to inspect the last line of the new heartbeat file. `phase: finished` means this particular child survived long enough to complete. An early final timestamp indicates it stopped; compare that timestamp with when you closed the terminal. A missing file may mean child launch was denied. Record output/errors rather than changing permissions blindly.

This is only a smoke test. It does not establish restart after server reboot, application-pool recycle behavior, service supervision, permitted hosting use, memory limits or IIS routing. Those must still be verified before hosting Django. Do not leave a terminal, scheduled task or ad-hoc detached process as the production supervisor. Probe files contain no clinical data and can be deleted after inspection.

## Database discovery

The user has confirmed MariaDB and MSSQL Server are available. In Plesk's MariaDB administration interface, run the read-only SQL `SELECT VERSION();` and report the version. Django 5.2 supports MariaDB 10.5 and later through its MySQL backend, as documented in [Django's database reference](https://docs.djangoproject.com/en/5.2/ref/databases/). Prefer a currently maintained server release, not merely the oldest supported one.

The project currently requires PostgreSQL in production. A MariaDB adaptation must cover driver installation, migrations/index/collation behavior, and concurrent quota/idempotency tests against the actual database. Do not point PostgreSQL settings at MariaDB or assume the existing PostgreSQL CI proves compatibility.
