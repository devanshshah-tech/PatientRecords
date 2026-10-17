# India Windows deployment runbook

This is a deployment plan; no remote server has been accessed or changed. Confirm OS, patched Python, RAM, disk capacity, network, domain and backup target before selecting service tooling. Keep credentials out of chats and repository files.

## Known Plesk subscription constraints

The user reports the Platinum subscription for `app.ahmcsrksm.in`: 2 GB disk allocation, overuse allowed, IIS application pool/ASP.NET enabled, SSL/HTTPS redirect enabled, MySQL/MariaDB and MS SQL databases, remote backup permission, and 100 MB per mailbox. These settings indicate Windows/IIS hosting but do not establish administrator access to a dedicated server. Overuse allowed is not a capacity or pricing commitment from the provider. SSL permissions are not proof that the installed certificate is valid and renewing successfully.

Provider confirmation is required for Python 3.12 virtual environments, dependency installation, long-running WSGI/Waitress process management, IIS reverse proxy support, runtime environment variables, private writable storage, CPU/RAM limits, shell/RDP access, and a supported PostgreSQL database. The current app production settings require PostgreSQL; MySQL or MS SQL will require a deliberate, tested database adaptation if PostgreSQL cannot be provided. Do not use a scheduled task as an improvised production process supervisor.

Plesk's current [Python extension](https://www.plesk.com/extensions/python/) lists platform `unix`; do not assume that it enables Django on this Windows subscription. Windows deployment requires a provider-supported Python integration or administrator-managed service/proxy arrangement.

Use an existing clinic-controlled external email address for setup/operations contact for now. Neither submissions nor manually entered intern invitations need SMTP. A domain mailbox can be added later for non-clinical notifications, after SMTP settings and delivery are tested; the 100 MB mailbox must never become a patient archive.

Production domain settings:

```text
DJANGO_ALLOWED_HOSTS=app.ahmcsrksm.in
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.ahmcsrksm.in
```

Google callback: `https://app.ahmcsrksm.in/accounts/google/login/callback/`.

## Runtime layout

Internet -> HTTPS reverse proxy -> Waitress bound to `127.0.0.1:8000` -> Django -> local PostgreSQL and private photo disk (or private S3 endpoint).

Use a dedicated unprivileged service account, a current patched Python 3.12, supported PostgreSQL, and a Windows service wrapper with restart-on-failure and rotating logs. Select and review the service wrapper once the server OS is known. Restrict filesystem ACLs to service and backup accounts. Encrypt the patient/backup disks using the server's approved encryption facilities. Only expose HTTPS and the chosen HTTP-to-HTTPS redirect; PostgreSQL, Waitress and storage management ports must remain private.

Configure an HTTPS reverse proxy such as Caddy or existing IIS. Set a request body cap of 26 MiB and upload/read timeouts; strip and replace `X-Forwarded-Proto`. The application must never trust this header from arbitrary clients. Disable request-body logging and query logging containing clinical data. HTTPS is required for mobile camera access.

Example Caddyfile (replace the domain; validate against the installed Caddy release before use):

```caddyfile
records.example.org {
    request_body {
        max_size 26MB
    }
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-Proto https
    }
}
```

Run Waitress with the same cap even if the proxy is misconfigured:

```powershell
.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=8000 --threads=4 --max-request-body-size=27262976 patientrecords.wsgi:application
```

Choose thread counts only after memory/load testing. Uploads and compression use memory; each concurrent image decode may consume tens of MiB. Waitress may buffer request bodies into temporary files; secure and encrypt its service-account temporary directory as well as the photo disk. No global Windows temp permissions should be weakened.

## Environment and preparation

Configure service environment variables from `.env.example`. Require `DJANGO_DEBUG=false`, a fresh random `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`, PostgreSQL credentials and an absolute `PRIVATE_MEDIA_ROOT` outside the website root. Enable `TRUST_HTTPS_PROXY=true` only behind the local trusted proxy. The app loads `.env.local` and `.env` without overriding service variables; set `DJANGO_LOAD_ENV_FILES=false` on hosts using only injected environment variables. Never upload development environment files to the public document root.

Rotate the old Django, database and email credentials from Git history, and any reused OAuth credentials. Do not reuse the removed values. Restrict the DB account to the app database; use separate backup/admin credentials.

Install `requirements.lock`, then back up any preexisting database before running migrations. Existing Heroku/mailbox records need a separate controlled import, patient-ID mapping, verification and reconciliation plan. These migrations create the new clinical tables; they do not recover old email attachments.

```powershell
.venv\Scripts\python.exe manage.py migrate --noinput
.venv\Scripts\python.exe manage.py collectstatic --noinput
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py check --deploy --fail-level WARNING
```

Google OAuth must use the exact production callback `https://YOUR-DOMAIN/accounts/google/login/callback/`. Set the Django Site domain/name for site 1. Add intern grants and doctor permissions through admin. Configure MFA for Google accounts and the admin access path before launch; app-enforced admin MFA is still outstanding. Rate-limit login, uploads and photo delivery at the reverse proxy; select thresholds during pilot/load testing.

## Release gates

1. All CI checks pass on the release commit, including PostgreSQL concurrency tests and dependency audit. No production credentials in CI.
2. HTTPS and OAuth tested end to end; direct public HTTP/DB/storage access denied. `check --deploy` passes with real service environment.
3. Test real Android Chrome and iPhone Safari: consent, camera denied, rear camera, repeated captures, remove, background/tab close, successful save, expired session, offline failure and safe retry. The app cannot prevent OS-level screenshots.
4. Clinician approves image detail, orientation and before/after workflow. Confirm patient-ID uniqueness and lawful consent/retention/deletion procedures with the clinic.
5. Load test on actual server; verify disk alerts and request limits. Reconcile storage after simulated process failure. Implement approved retention/deletion operations.
6. Encrypted off-server backup and documented restore succeed with database + photos + manifest, and a restored comparison actually works. Agree recovery-point/recovery-time targets.
7. Start a small cohort, record operational failures without clinical payloads, review weekly, and expand only after fixes.

Deployment is manual until server identity and secure access are configured. Never attach a production self-hosted runner to untrusted pull-request jobs. For GitHub Free, use hosted CI with synthetic data and cancel superseded builds; confirm your account's included minutes rather than assuming unlimited private-repository execution.

## Rollback

Record deployed commit and dependency lock. Stop submissions before rollback; preserve database and media snapshots. Never blindly roll back schema migrations that contain clinical data. Restore into a separate location first, verify manifests and protected photo delivery, then switch the service. Keep retained newer submissions available for authorized reconciliation.
