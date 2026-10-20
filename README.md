# Clinical patient records

Django application for invited interns to capture consented clinical photos, and authorized doctors to retrieve records and compare dated photographs. Photographs are stored privately; submissions never send clinical details or attachments to email.

Start with [SPEC.md](SPEC.md) for scope and launch gates, and [AGENTS.md](AGENTS.md) for engineering rules. Windows deployment: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Storage decisions: [docs/STORAGE.md](docs/STORAGE.md).

Actual test evidence and remaining gates: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Local development (PowerShell)

Use a currently patched Python 3.12 installation. Do not use real patient records in development.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:DJANGO_DEBUG = 'true'
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver
```

An existing `.venv` can be reused. Set Google OAuth client credentials in environment variables for intern sign-in; configure the localhost callback `/accounts/google/login/callback/`. Copy `.env.example` to `.env.local` for local settings. The app loads `.env.local`, then `.env`, without overriding shell/service variables. Both real environment files are ignored by Git. Set `DJANGO_LOAD_ENV_FILES=false` to disable loading them.

## Neon and npm commands

The app keeps Django's PostgreSQL backend and psycopg 3. Neon supplies pooled `DATABASE_URL` for normal application traffic and `DATABASE_URL_UNPOOLED` for migrations. URLs require TLS; server-side cursors and automatic prepared statements are disabled for pooler compatibility. Configure services in `neon.ts`; `neon deploy` applies database-service configuration and pulls secrets locally, not the Django website itself.

```powershell
npm.cmd install
npm.cmd run build
npm.cmd test
npm.cmd run test:camera
npm.cmd run db:migrate
npm.cmd start
```

`build` runs Django checks, migration consistency and static asset collection. `test` deliberately disables local dotenv loading and removes database URL overrides, so ordinary tests use an isolated SQLite database. `db:migrate` requires the direct URL. `start` runs Waitress on localhost port 8000 by default; a managed host sets `BIND_HOST=0.0.0.0` and `PORT`. Set `PATIENTRECORDS_PYTHON` if Python is not in `.venv` or on PATH.

Project-scoped Neon MCP configuration uses OAuth and an explicit project scope, with no API key in Git. It may require an agent restart and browser authorization before MCP tools become available. CLI authentication is separate from MCP authorization.

See [docs/NEON.md](docs/NEON.md) for the linked project, service scope and live SQL/HTTP verification procedure.

Admin login is `/admin/`. Add an intern access record with their exact Google email and a reason; default expiry is one calendar year. Edit expiry to extend access for repeat exams, or revoke the grant. Expiry is checked on every submission, even for existing sessions. Never share accounts.

For a semester roster, use **Invite semester interns** on the Intern Access admin list and paste one email per line. Existing grants are preserved; extensions and revocations are deliberate individual edits. Grant creation and modifications record an audit event.

Give doctors the `users | patient | Can review patient photographs and compare visits` permission. To manage invitations, also grant staff status plus view/add/change InternAccess permissions; clinical permission alone does not grant admin access. Bootstrap a doctor via an intern invitation for their first Google login, then assign the doctor permission. Superusers have all permissions; reserve them for administration.

Doctor routes: `/doctor/` for search; `/doctor/compare/` for side-by-side photographs. Search accepts patient ID, name, OPD, case year, diagnosis. Interns have no record browsing route. Images are streamed through an authorization check, never through public media URLs.

Camera capture requires HTTPS except on localhost. The app does not save captures to the mobile gallery. A browser cannot prohibit screenshots or copying by a modified client. Test actual mobile browsers over HTTPS before launch.

## Verification

```powershell
$env:DJANGO_DEBUG = 'true'
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test users
.venv\Scripts\python.exe manage.py collectstatic --noinput
node --check static/users/camera.js
node --test tests/camera.test.cjs
```

CI verifies SQLite on Windows and PostgreSQL on Linux, including concurrent quota reservations. It uses synthetic data and no live credentials, and is configured locally until pushed. GitHub Actions usage depends on your plan's available minutes; the workflow has timeouts and cancellation to limit waste. Deployment remains a manual gated release. Dependabot proposes dependency updates; merge only after checks and review.

Dependencies: `requirements.txt` lists intentional direct dependencies, `requirements.lock` pins their installed dependency closure for reproducible builds. Refresh the lock after reviewed upgrades, not from an unrelated environment's entire `pip freeze`.

## Launch status

Development foundation, not yet a production deployment. Rotate every credential previously committed to settings; removal from the current file does not remove it from Git history. Existing mailbox records are not imported. Server capacity, real-device capture, clinical compression approval, S3 backend integration, PostgreSQL CI results, MFA, retention/deletion policy, backups/restore and load tests are launch gates. Database/file cleanup handles ordinary transaction failures; a process crash can leave orphan files, which require reconciliation before production.
