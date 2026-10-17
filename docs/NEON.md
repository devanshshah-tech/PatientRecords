# Neon integration

Requested configuration: organization `org-wild-forest-66608257`, project `delicate-wind-71461620` (`Records`), branch `production` (`br-soft-block-b3c5agoi`). The CLI confirmed AWS Singapore (`aws-ap-southeast-1`) and PostgreSQL 17. Only Postgres is enabled; Django retains its existing authentication and photo storage implementation.

Here, "branch" means a Neon database branch, independent of Git branches and commits. No repository commits were created or pushed during this setup. `neon deploy` configures Neon services; it does not publish the application code.

## Tooling

Neon CLI 8.4.5 was installed with `npm i -g neon@latest`. The user completed browser login. Setup used:

```powershell
neon.cmd init -y --org-id org-wild-forest-66608257 --project-id delicate-wind-71461620 --branch production --services postgres --agent codex --skill neon --mcp-auth oauth --mcp-config-location project --mcp-project-scoped
neon.cmd config plan
neon.cmd deploy
```

The plan and deploy reported no changes, with `Utilized services: Postgres`. The CLI generated `neon.ts`, ignored `.neon` context and ignored `.env.local` credentials. `.codex/config.toml` configures the Neon MCP URL scoped to this project using OAuth; it contains no API key. The MCP server is not automatically added to the tools of an already running agent session. Its first use may require separate browser OAuth consent; CLI login does not prove MCP authentication.

Installed skills: neon, neon-postgres and neon-postgres-branches. Sources: [Neon skill](https://neon.com/.well-known/agent-skills/neon/SKILL.md) and [Neon CLI](https://neon.com/docs/cli).

## Application wiring

`patientrecords/settings.py` loads `.env.local`, then `.env`, without replacing shell/service values. `DJANGO_LOAD_ENV_FILES=false` disables local file loading. Neon credentials remain ignored by Git; never print or copy them into issue reports.

The ordinary Django PostgreSQL backend uses psycopg 3. `DATABASE_URL` selects the pooled connection for request traffic. TLS is mandatory for URL-based connections; cursor/session settings are compatible with transaction pooling. `DATABASE_URL_UNPOOLED` is selected when `DJANGO_DATABASE_UNPOOLED=true`, used by the migration command. Existing split `DB_*` settings and development SQLite still work.

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd test
npm.cmd run test:camera
npm.cmd run db:migrate
npm.cmd start
```

Python dependencies must already be installed in `.venv` from `requirements.lock`, or the configured `PATIENTRECORDS_PYTHON` interpreter. The local ignored env file enables `DJANGO_DEBUG=true` for localhost development. Live hosting needs a new secret key, `DJANGO_DEBUG=false`, explicit hosts/CSRF origins and the remaining production security gates.

`npm run build` runs Django system checks, migration consistency checks and static-file collection. It does not provision a website or migrate the database. `npm test` disables dotenv loading and removes remote database URL/name overrides so ordinary tests use SQLite. `npm run db:migrate` explicitly uses the direct database URL. `npm start` serves through Waitress on localhost; a managed web host sets `BIND_HOST=0.0.0.0` and its assigned `PORT`.

## Live verification

Run `.venv\Scripts\python.exe scripts/verify_neon.py` after Neon CLI login. It checks the linked production pooled connection using read-only SQL, creates a schema-only verification branch with two-hour expiry, runs migrations and all Django regressions there, starts Waitress, then tests a synthetic upload, doctor search, private image delivery, intern denial and access revocation through actual HTTP. It removes the disposable branch afterward. No production rows are copied. The production env file/context remains linked to production; test URLs are injected only into verification processes.

Verification photos use a temporary private filesystem directory. This does not verify R2 or Google Drive; neither is provisioned by the Postgres-only config. Live Google OAuth sign-in also needs its own browser/client configuration check. A publicly reachable Django web service and DNS for records.bulkhead.cc remain separate hosting work.

### Completed on 15 October 2026

The full live verification passed: 30 Django/PostgreSQL tests, followed by actual HTTP upload, doctor search/private image retrieval, intern denial and immediate grant revocation. Both disposable verification branches were removed. After verification, `npm run db:migrate` applied all application migrations to the linked production branch; `manage.py migrate --check --noinput` exited successfully. No synthetic patient records were written to that branch. The final build passed and `npm start` started the configured application locally. See [VERIFICATION.md](VERIFICATION.md) for failures, fixes and remaining launch gates.
