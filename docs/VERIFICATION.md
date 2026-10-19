# Verification record

## Save-failure investigation and private diagnostics - 18 October 2026

Investigated an operator-reported generic save failure. Verified the live database connection, matching deployed/local Drive authorization, both untrashed writable location folders and private root, and absence of duplicate patient/visit folder groups. No partial clinical rows remained. Existing logs had no retained failure category because handled errors were swallowed. A real synthetic 10-image intern save and one-image doctor save passed, including confirmations, retry/idempotency, invalid-image no-visit behavior and access checks; all synthetic files/records were cleaned up. The original failure was not reproduced and its cause is unconfirmed.

Added allowlisted Drive operation/error categories and HTTP status plus database/filesystem categories to warning logs, without exception text, stack traces, provider bodies, patient inputs, URLs or credentials. Wrapped write errors preserve their diagnostic category after cleanup. Public error wording is unchanged. Local verification: 70 Django tests completed (68 passed, two PostgreSQL-only skips), build/system and migration consistency checks passed. Regressions verify provider-body/patient-name exclusion, unknown-reason rejection and preservation of the original upload diagnostic. No schema changes.

## Intern batches and audited deletion controls - 18 October 2026

Added a batch label, batch search/filter, 100-row pages, select/clear controls and an explicit delete-selected button using Django's native CSRF-protected confirmation. Single and bulk deletion require delete_internaccess permission. Deletion audits each prior grant and removes the selected snapshot in one transaction; accounts and clinical records remain. New roster invitations require a consecutive-year batch, while repeated invitations preserve existing batch, dates, revoked state and reason. The migration backfills existing labels with fixed 2026-2027 before enabling the current-academic-year default; it does not update any date columns.

Local verification: 68 Django tests completed (66 passed, two PostgreSQL-only skips). Tests cover confirmation-before-delete, active-session denial after deletion, preserved accounts/clinical history, filtered select-across isolation, permission denial, audit rollback and batch validation/preservation. Build/system and migration consistency checks passed. An in-memory admin-control check verified select/clear and submission through the native confirmation action. Verified the live target contains 95 grants and saved only a hash/count baseline of all existing non-batch access fields in ignored operator tooling. Deployment must compare that baseline afterward; live smoke deletion uses synthetic grants only.

## Photo-limit message visibility - 18 October 2026

Attempting an eleventh capture now smoothly scrolls and focuses the message immediately above the captured image queue: remove a photo below before taking another. Existing ten captures are retained. The camera status is programmatically focusable. All eleven existing camera tests and the build passed; an in-memory browser-harness check additionally verified the ten-photo boundary, scroll/focus, preserved queue and successful replacement after removal. No database/model changes or clinical data were involved.

## Persistent save confirmation and plain retry feedback - 18 October 2026

Replaced the short-lived homepage flash message with a private confirmation page showing the saved patient name and actual persisted image count. JSON and ordinary POSTs go to the same opaque submission-UUID destination. Only the uploader with currently active access can view it; names are escaped, no clinical details go into flash cookies or URL parameters, and reloads/idempotent retries retain the correct original count. The form shows saving progress, brings failures into view and focuses them, retains captures on failure, and hides technical network/JSON/server details behind plain retry instructions. Known storage/database failures return the form with a helpful message; validation guidance remains available.

Local checks: 63 Django tests completed (61 passed, two PostgreSQL-only concurrency skips); camera regressions cover persistent navigation, malformed responses, bad destinations, server failure and connection loss with successful retry. Build/system checks, migration consistency and whitespace checks passed. No model migration is required. The save service also rejects an empty photo queue or empty image payload before creating patient/visit rows. A targeted partial-upload regression verifies that a failed second Drive photo removes the first uploaded file, rolls back all visit/photo/audit rows, removes a newly created patient, and preserves an existing patient's previous quota. Live release verification follows CI.

## Location-specific cases and descriptive folders - 18 October 2026

Preserved the operator's reordered consent field and made the new tf_shift checkbox optional (unticked Anand Hospital, ticked Tribhuvandas Foundation). Added numeric six-digit padding, location-scoped patient identities/quotas, persisted visit indices, first-visit patient folder naming and per-visit reason/intern labels. Doctor search and comparison include location. Existing opaque photo URLs and references remain private and valid; existing files are not moved. Guarded migration normalizes numeric legacy cases, aborts on collisions and backfills chronological visit indices. The two sites use separate case records, as confirmed by the operator.

Local verification: 58 tests completed, 56 passed and two PostgreSQL-only concurrency tests skipped; nine camera tests passed. Build/system checks, migration consistency and whitespace checks passed. Coverage includes padded matching, optional shift, same-number location isolation, comparisons excluding other-site photos, stable first-folder labels, safe storage paths, replay protection and collision-safe legacy normalization. PostgreSQL CI also runs concurrent visit-index allocation and quota enforcement. No actual clinical records were used in tests. Drive lookup found the manually created site folders were not visible to drive.file; the setup command created app-managed private children of the existing root without touching those folders or photos. GitHub CI and live release verification follow before deployment is considered complete.

## Spreadsheet intern invitations ? 17 October 2026

Capitalization was already normalized. Expanded roster parsing to accept spreadsheet tabs and whitespace plus comma/semicolon separators, retaining newline columns, duplicate removal, the 500-unique-address limit and all-or-nothing validation. Invalid input now identifies line numbers without echoing account lists; results distinguish new grants from existing ones. Regression covers Excel CRLF/tab pastes, mixed-case duplicates, multiple invalid lines and no partial grant creation. Local suite: 51 tests completed, 50 passed and one PostgreSQL-only concurrency skip. Build checks and migration consistency passed with synthetic development settings. The first dotenv-disabled build omitted DEBUG/SECRET_KEY and failed closed as intended; rerunning with explicit development DEBUG passed. No live roster or access grants were changed during testing.

## Visit navigation, upload feedback and test reset ? 16 October 2026

At the operator's request, removed all public-preview clinical rows: one patient, two visits and six photo references. Preserved accounts and access grants, and left the original Drive files for the operator to remove. Removed the preview Neon branch expiration; no scheduled expiry remains. Free usage remains subject to provider quotas and terms.

Separated private single-visit galleries from patient-wide comparisons, grouped search results per patient, and added visible back/home links. Age remains a snapshot per visit. Fixed fetch consuming the upload success message by returning a JSON 201 navigation response; ordinary form submissions retain redirects and validation failures remain visible. Local verification: 50 Django tests completed (49 passed, one PostgreSQL-only concurrency skip), nine camera tests passed. Regression tests cover single-visit isolation, doctor/intern authorization, private caching, grouped comparisons and success feedback after navigation.

Release `77ff35d` passed Windows and PostgreSQL CI (39011733753 and 39011731433) and deployed as `dep-db9hu6ajnfac73cc0g50`. Live HTTPS checks passed JSON success feedback after navigation, private Drive persistence/delivery, intern denial, retry idempotency, two visits grouped under one patient and isolation of individual galleries. Synthetic verification files and rows were cleaned up; final public counts are zero patients, visits and photo references.

The initial sandbox build could not reach Neon; rerunning with network permission passed. The first staged secret scan lacked Git safe-directory configuration; the corrected scan passed. The first live form request timed out before uploading; the longer-timeout retry passed.

## Capture removal count and Drive preview activation — 16 October 2026

Fixed stale capture counts by updating the live status on both capture and removal, with singular/zero states. Added the reported four-to-one removal and subsequent capture regression; all eight camera tests passed. All 48 Django tests completed (47 passed, one PostgreSQL-only concurrency test skipped). Updated the preview notice to describe saving availability dynamically instead of always saying storage is unavailable. The preview database has no legacy filesystem photo references, so Drive activation needs no reference migration. Synthetic-only guidance remains until the clinical launch gates pass.

## Workspace doctor account — 16 October 2026

Provisioned the operator-requested clinic Workspace identity as a doctor/admin in both the local-linked and isolated public-preview databases, preserving prior accounts and intern grant dates. Removed the provisioning command's Gmail-only limit. Email linking now accepts Google-verified Workspace addresses carrying Google's hosted-domain claim, while requiring the same unique active preauthorized account and explicit doctor permission. Synthetic regression covers successful Workspace lookup, verification persistence, absent hosted-domain denial and unverified-email denial. All 48 tests completed (47 passed, one PostgreSQL-only concurrency test skipped). Real account emails and credentials are not committed.

The user then completed browser authorization for the exact verified storage owner. `connect_drive` created the private app root and saved credentials only in ignored `.secrets`; `verify_drive` passed real API synthetic JPEG upload, byte-for-byte read-back and file deletion. An explicit offline refresh-token exchange also passed without logging token values. Empty test folders remain as documented. The filesystem backend and Render preview upload block are unchanged; credentials are not deployed to Render. Workspace login fix CI passed on Windows and PostgreSQL in runs 39004398308 and 39004400624.

## Public preview preparation — 16 October 2026

User authorized GitHub publication, CI, Render preview and the records.bulkhead.cc domain before Drive authorization. Added a schema-only preview database without copied records, preview guidance, a server-side submission kill switch, a camera-only UI, a health endpoint, and managed-proxy HTTPS handling. Render Blueprint validates. Gitleaks staged scan passed. Local Django tests: 47 discovered, 46 passed, PostgreSQL-only concurrency test skipped. Camera tests: 7 passed, including preview capture without any outgoing upload. GitHub and Render release evidence is recorded after remote verification; Drive remains disconnected and clinical launch gates remain pending.

The first GitHub run (38990584448) passed clinical regressions on Windows and PostgreSQL but failed the separate CSRF template tests because a clean runner had no collected static manifest. The local manifest had hidden that test dependency. Corrected the isolated test class to use Django's plain static storage; production manifest storage remains unchanged.

## OAuth My Drive backend — 16 October 2026

Added optional `PHOTO_STORAGE=drive`, private OAuth-backed upload/read/delete, opaque patient/visit folders and short file-ID references. Added operator-only Desktop OAuth setup with exact verified-owner checking, offline credentials in ignored `.secrets`, and a synthetic verification command. Setup never changes the active storage setting. Existing filesystem references fail explicitly until migrated; account-wide Drive permission and public file links are not used.

`npm test`: 46 discovered, 45 passed, one PostgreSQL-only concurrency test skipped. New tests cover bounded/private reads, unsafe paths, app-owned metadata checks, preallocated-ID cleanup after ambiguous upload failure, actual Django file-reference persistence, and transaction rollback. Initial tests found a mismatched path-traversal exception assertion, string UUID conversion, and Windows path separator normalization; corrected all three and reran successfully. `npm run build` passed; no migration drift. `pip check` passed; dependency lock updated to 35 packages. Git ignores both OAuth client and token files.

No Desktop client JSON is present yet, so browser authorization, real API upload/read/delete, Drive-backed HTTP delivery and offline refresh remain unverified. Storage remains filesystem. Existing test photos need an explicit migration or isolated clean pilot before switching. Hard-crash reconciliation, credential lifecycle alerts and backup/restore remain production gates. See GOOGLE_DRIVE_SETUP.md.

## Clinical identifier labels — 16 October 2026

Updated submission labels to UHID / Case No. (required), Aadhar/ABHA ID (optional), and Previous UHID / Case No. (optional). Doctor search/comparison use matching terminology and omit empty Aadhar/ABHA values in summaries. Existing storage keys and records are preserved; the Visit field's blank flag is updated through migration 0002. Extended the successful upload regression to omit Aadhar/ABHA entirely and verify the empty value persists. All 40 tests completed (39 passed, one PostgreSQL-only concurrency test skipped).

## Wrong Google account recovery — 15 October 2026

Denied Google identities now redirect away from the one-use OAuth callback to `/access-denied/`, a themed non-cacheable HTTP 403 page with a CSRF-protected retry form and home link. Google authorization requests include `prompt=select_account` so retrying offers account selection. Identity conflicts also use this generic recovery page without exposing account details. Added regression coverage for denial redirect, recovery controls, no-store headers, no user creation, protected-route denial and the actual retry redirect's account-selection parameter. All 40 tests completed (39 passed, one PostgreSQL-only concurrency test skipped). A browser round trip through Google remains a manual check.

## Login success notification consistency — 15 October 2026

The previous name change missed allauth's separate `user_display` notification hook. Configured it to use the same name/permission-derived role helpers as the homepage. The existing synthetic intern test now renders the actual login success template and asserts the name and role replace the username. All 39 tests completed (38 passed, one PostgreSQL-only concurrency test skipped). Restarted the app; newly generated login messages use the shared label.

## Signed-in identity display — 15 October 2026

The homepage now shows the full name and permission-derived Intern or Doctor/Admin role, with an inactive label where access has ended. Internal generated usernames are never the fallback. Authorized Google login fills missing first/last names from the provider profile, preserving existing names. Extended the pre-created-intern regression to verify persisted synthetic names and the rendered role. All 39 tests completed (38 passed, one PostgreSQL-only test skipped); build passed. Existing nameless accounts require a fresh Google login to populate names.

## Hospital sign-in branding — 15 October 2026

Replaced the provider-default login page with the shared clinical layout and a responsive sign-in card, invited-account guidance and access help. The shared layout displays the supplied Anand Hospital logo and favicon; allauth entrance pages also inherit the local theme. Build passed with no migration drift. All 39 Django tests completed (38 passed, one PostgreSQL-only concurrency test skipped). The restarted page and its logo/favicon/CSS returned HTTP 200; the login retains its POST form and CSRF token. No browser screenshot/physical-device visual inspection was available in this session.

## Pre-created intern verification regression — 15 October 2026

The operator-provisioned intern invitation was active and unexpired, but Google email authentication did not persist an `EmailAddress` for the existing account. The subsequent request-time verification gate correctly rejected the session. Fixed the social-login adapter to persist only an authorized, Google-verified email matching the existing account, with conflicting ownership rejected. No invitation-only verification or manual verification of real accounts was performed. Added regressions for the complete pre-created-intern lookup/authorization/protected-route/revocation sequence, unverified-provider denial, and conflicting ownership. `npm test`: 39 discovered, 38 passed, 1 PostgreSQL-only concurrency test skipped. The user must sign out and complete a fresh Google login to provide verification evidence.

## Preauthorized local Google accounts — 15 October 2026

Confirmed the ignored `.env.local` Google client ID and secret are populated and loaded, without printing their values. Restarted the local app. An actual CSRF-protected POST to the Google login endpoint returned a Google redirect containing the expected nonempty client ID and the registered loopback callback. This verifies request construction, not Google's acceptance or completion of browser consent.

Added restricted preauthorized-account email authentication: only Google-verified Gmail identities matching exactly one active local account with a current invitation or explicit doctor permission qualify. Other providers, unverified identities, staff-only accounts and ambiguous emails are rejected. Added an operator provisioning command for separate admin/doctor and intern roles; it never marks email verified or sets shared passwords. Applied the operator-requested account setup without storing account emails in source. Added synthetic regressions for this bootstrap and role separation. `npm test`: 36 discovered, 35 passed, 1 PostgreSQL-only concurrency test skipped. No schema changes; real browser sign-in still requires the configured Google test users and exact callback URI.

## Local Google login CSRF fix — 15 October 2026

An actual browser form submission failed with `Origin: null`. Both the response header and base HTML used `no-referrer`, which can suppress form origins. Changed both to `same-origin`, retaining external referrer privacy and normal CSRF enforcement. Added regressions for the actual header/template, HTTP/HTTPS same-origin POST acceptance, HTTPS referer fallback, and rejection of null/external origins and missing tokens. `npm test`: 33 discovered, 32 passed, 1 PostgreSQL-only test skipped. The first new-test run failed because the isolated test URL configuration lacked the base template's `index` route; corrected the fixture and reran successfully. No database/schema changes. A real browser Google OAuth round trip is still pending.

## Neon integration — 15 October 2026

Neon CLI 8.4.5 linked the requested organization/project and production branch, enabled only Postgres, and pulled credentials into ignored `.env.local`. `neon deploy` reported `No changes` and `Utilized services: Postgres`. Project metadata confirmed AWS Singapore and PostgreSQL 17; live TLS SQL reported PostgreSQL 17.11.

- `npm run build`: system checks passed, no migration drift, static collection completed.
- `npm test`: 30 discovered, 29 passed, 1 PostgreSQL-only concurrency test skipped on SQLite.
- `npm run test:camera`: 6 passed.
- `scripts/verify_neon.py`: all 30 Django tests passed on a disposable schema-only Neon branch, including concurrent quota enforcement (`Ran 30 tests in 282.437s`, `OK`).
- The script started Waitress and exercised actual HTTP: homepage 200, consented synthetic upload persisted through Neon, intern image request 403, doctor search and private JPEG delivery 200 with `no-store, private`, and a revoked existing intern session 403.
- Verification branches were deleted, including after the failed first attempt. Production rows were neither copied nor used as test data. Photographs used temporary private filesystem storage.
- After isolated verification, `npm run db:migrate` applied the application schema to the linked production branch successfully. `manage.py migrate --check --noinput` exited 0. No synthetic clinical records were inserted there.
- `pip check` passed. The updated 30-package Python dependency lock had no known vulnerabilities in the audit; npm reported zero vulnerabilities.

The first PostgreSQL run failed with nine closed-connection errors after a test directly closed a streaming response. Corrected that test to consume Django's wrapped streaming iterator, avoiding closure of its shared test transaction. The complete PostgreSQL rerun above passed. Two optional table-count shell probes failed due to PowerShell/native argument quoting before executing SQL; schema verification instead uses Django's migration commands.

The project-scoped OAuth MCP configuration was written and validated, but this agent session did not load the new MCP server, so MCP authentication/tool execution remains unverified. Reload the agent and complete browser OAuth if requested. CLI authentication and live application access are verified independently. Public hosting, DNS, Google OAuth browser sign-in, cloud photo storage and clinical launch gates remain outstanding.

## Earlier local baseline — 13 October 2026

Local environment: Windows, existing Python 3.11.2 virtual environment, SQLite test database, synthetic images/accounts only. Production guidance and CI target patched Python 3.12. No live server, mailbox or preexisting database was migrated; no GitHub workflow was executed remotely.

## Passed locally

- Django tests: 23 discovered, 22 passed, 1 skipped (PostgreSQL concurrency).
- Camera workflow: 6 Node tests passed, exercising consent/HTTPS, in-memory JPEG capture and resize, removal, failed-save retry, login redirect handling, and camera/preview cleanup.
- Django `check`: no issues.
- `makemigrations --check --dry-run`: no model drift.
- `check --deploy --fail-level WARNING`: no issues under synthetic production settings; this does not verify server networking or operational controls.
- `collectstatic --noinput`: completed successfully.
- JavaScript syntax check and Git whitespace checks: passed.
- `pip check`: no broken requirements.
- Pinned 28-package application dependency closure audited: no known vulnerabilities found by pip-audit. The first audit identified vulnerable cryptography 48.0.1; upgraded to 50.0.2 and reran successfully. A clean audit is not a guarantee against undiscovered defects.

Authorization tests include unlisted/unverified users, start dates, expiry, extensions, revocation of an existing session, staff without clinical permission, intern/anonymous image denial, and restricted semester invitation administration. Record tests cover required consent, private/non-cacheable image delivery, multi-visit patient linking, uploader identity, no email attachments, repeat-submission idempotency, quota rollback, file cleanup on a failed transaction, EXIF/orientation/resize, corrupt/animated images, upload bounds, search and same-patient comparisons.

## Pending launch gates

The PostgreSQL concurrency regression subsequently passed on Neon as recorded above. CI definitions and dependency updates must still be pushed and their actual GitHub results reviewed. Real S3 write/read/delete and policy tests are pending an endpoint. Synthetic Node browser mocks do not replace testing camera permission, capture quality and upload behavior on Android Chrome and iPhone Safari over HTTPS. Google OAuth needs an end-to-end test with the actual client configuration.

Before real data: rotate previously committed credentials, verify server capacity/TLS/network ACLs, enforce MFA and rate limits, obtain clinician approval of compression, agree retention/deletion and recovery targets, implement storage reconciliation for hard crashes, and prove encrypted off-server backups and restores. See SPEC.md and DEPLOYMENT.md for the complete rollout gates.

Release `79ebf75fccd69f951a736c83e2ab535a5cd8ee3d` passed both Windows/PostgreSQL CI workflows (39181955516 and 39181952899) and deployed live as `dep-dbamfns9v7es7393jg1g`. The local-linked database migration and consistency check passed too. The real Drive hierarchy check verified two Anand visits sharing the first patient folder, indices 1/2, and an independent Tribhuvandas case/index 1. Full HTTPS checks through the direct Render hostname passed padded doctor search, separate location groups, comparison isolation and intern photo denial. Synthetic photos/rows/accounts/grants/audits/sessions were cleaned up; empty synthetic folders remain.

The custom-domain run passed uploads and Drive hierarchy but then failed on a TLS connection reset while opening the doctor page. Its data was cleaned up. A bounded retry also failed at the initial form GET. Direct Render HTTPS health and the complete workflow passed. DNS currently resolves the custom domain to Cloudflare; custom-hostname TLS also failed from this machine when targeting the origin directly, so Cloudflare alone is not established as the cause. No DNS settings were changed, and custom-domain connectivity remains a verification limitation.

Save-feedback release `c64b258addf7c3bb9342a5596c81623b149808ff` passed both exact-release Windows/PostgreSQL CI workflows (39190909453 and 39190906279) and deployed as `dep-dbao68u1egvs73bfp4p0`. Eleven camera tests passed. Live HTTPS through the direct Render hostname verified named confirmation for an intern's ten images and a doctor's single image, persistence on reload, private cache headers, no clinical flash cookie, original count after a retry, no duplicate visit, invalid-image rejection without a new visit, cross-user denial and immediate revoked-access denial. Synthetic photos, patients, visits, accounts, grants, audits and sessions were cleaned up. The custom hostname still failed TLS from this machine, so the live check used Render directly; no DNS changes were made.

Intern batch release `4f8668f5c5506fd6627f918a8d6598d918b689af` passed both exact-release Windows/PostgreSQL CI workflows (39194106029 and 39194102137) and deployed as `dep-dbaopk5g1s2s73cu6fu0`. Review identified that Django's action scripts use div.actions internally; the custom toolbar uses its own class to preserve native selection semantics. Both local-linked and live migrations passed. The live roster remains exactly 95 entries, all labeled 2026-2027, and the before/after SHA-256 fingerprint of every original email/start/expiry/revoked/reason/PK matched. Enabled deletion only for the two existing active staff accounts already holding add/change access-management permissions; no ordinary staff received clinical permissions.

Live HTTPS admin checks through the direct Render hostname verified loaded selection controls/static script, filtered select-across confirmation without premature deletion, audited deletion of two synthetic entries, preservation of a different synthetic batch/account, and immediate denial of a preexisting intern session. Single deletion rejected a manager missing delete permission, then succeeded with confirmation after that permission was restored. Temporary accounts, grants, sessions and synthetic audit/admin logs were removed. The final real-roster fingerprint still matches and all 95 original entries remain. No real clinical records or Drive files were used or altered.

Diagnostic release `6acd9b84d81db1d701988e541bc94a51a6f724ef` passed exact-release Windows/PostgreSQL CI (39208535893 and 39208530640) and deployed as `dep-dbara9uq1p3s73cptn70`. A fresh synthetic live Drive save and named confirmation passed after deployment; its file, rows, account and session were cleaned up. No real records/files were modified. The earlier operator failure remains unconfirmed: weak client connectivity can interrupt uploads, but the exact server-generated save message does not establish Wi-Fi as the cause. Future handled failures now have privacy-safe diagnostics rather than silently losing the error category.


## Doctor photo viewer ? 19 October 2026

Added private lazy-loaded search thumbnails and a shared modal viewer on search/visit-detail pages, separate from comparison. Local build passed Django system checks, migration consistency and static collection. Django tests: 70 run, 68 passed and two PostgreSQL-only concurrency tests skipped on SQLite. Node: all 15 camera/viewer tests passed, including fit/zoom bounds, pointer pan bounds, resize, keyboard, Escape/X, focus/scroll restoration, load failure and external-link rejection. Django assertions verify private cache headers, thumbnail links and comparison exclusion; existing access tests cover denied users. No schema changes. Physical Android/iPhone interaction remains to be checked; synthetic DOM tests cannot establish device rendering/touch behavior.

Viewer release `b160601d6dc1fcf7e26b33ab0162366755442e85` passed both exact-release Windows/PostgreSQL CI runs (39340186436 and 39340182179), including the PostgreSQL concurrency tests, production settings gate and dependency audit; staged secret scan passed. Render deployment `dep-dbba8ue7bikc73fpvthg` is live. Direct Render HTTPS synthetic checks passed search/detail viewer markup and static asset delivery, doctor photo access with private/no-store headers, intern/anonymous denial and comparison exclusion. The synthetic Drive file, patient/visit/photo rows, accounts, grant, audit rows and sessions were removed; empty synthetic folders remain. No real records were used or modified. No custom-domain DNS changes. CLI status inspection initially used an unsupported --limit flag, then used the supported list command; deployment itself succeeded.


## Recent visits ? 19 October 2026

Added doctor-only Recent visits navigation, default India calendar day, inclusive date range validation, latest-first stable ordering, both hospital labels, 25-visit pagination and photo counts without downloading images. Back to home is always visible; visit detail returns to the selected dates/page. Added a composite timestamp/ID index migration, without changing record contents or access dates. Local Django suite: 74 tests, 72 passed and two PostgreSQL-only concurrency skips. All 15 Node camera/viewer tests passed; npm build passed system checks, migration consistency and static collection. Regression coverage includes India/UTC midnight boundaries, inclusive end date, same-time tie ordering, pagination, empty/invalid ranges, return navigation, private cache headers, ordinary staff/intern/anonymous denial and permission revocation.

Recent visits release `ce8c317eb9ea0ce1e54108fa7f5586f375c7c1a8` passed exact-release Windows/PostgreSQL CI (39343285587 and 39343281804), including migration application, full PostgreSQL concurrency tests, deployment security settings and dependency audit. Secret scan passed. Render deployment `dep-dbbaml8m7kps73e9cnmg` is live. Synthetic direct-Render HTTPS checks passed default India today, explicit date selection, excluded dates, invalid-range guidance, private cache headers, visit-detail/back-to-selected-range navigation, home button and intern/anonymous denial. Removed the synthetic Drive photo, patient/visit/photo rows, accounts, grant, sessions and audit rows; empty synthetic folders retained. No real records/files or access grants were changed.
