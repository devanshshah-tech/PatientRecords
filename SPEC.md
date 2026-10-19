# Patient records revival

## Scope and decisions

Replace Gmail as the record store with PostgreSQL records and private, compressed photographs. The selected database is now Neon in Singapore; web hosting is being evaluated on Render and the intended domain is records.bulkhead.cc. Private filesystem storage works locally, with an optional S3-compatible backend for a future private Cloudflare R2 bucket. Email is optional account infrastructure, never the clinical archive. The provisional quota is 50 MiB of compressed images per patient across all visits, rather than 50 MB of duplicated sent/received mail. Confirm this quota and retention policy with the clinic before production.

Patients are linked by a clinic-issued ID. Submissions retain the existing OPD, diagnosis, and intern fields, timestamp, uploader identity, and explicit consent. Do not infer identity from a patient name. Interns cannot browse records. Authorized doctors/admins search by patient ID and choose dated photographs for side-by-side comparison.

The current form labels are UHID / Case No. (required), Aadhar/ABHA ID (optional), and Previous UHID / Case No. (optional). Existing internal keys `patient_id`, `opd_number`, and `previous_opd_number` remain for compatibility; older OPD values are not converted into identity numbers. Doctor search and comparison use the current labels as well. Optional Aadhar/ABHA values may be saved empty.

Doctor retrieval also supports exact OPD/case-year filters and partial patient-name/diagnosis search, replacing the old email-subject convention. PostgreSQL indexes patient IDs and OPD/year columns. Storage is swappable between private files and a private S3-compatible endpoint. MinIO community upstream is archived as of the current review; lakeFS is an extra versioning layer, not the underlying store. See docs/STORAGE.md for evaluated options.

Operator provisioning may create a doctor account before its first Google login. Email authentication may match exactly one active, preauthorized local account only when Google verifies the matching Gmail address or Workspace identity with Google's hosted-domain claim. Unverified identities, third-party addresses without that claim, other providers, ambiguous matches and ordinary staff accounts cannot use this bootstrap path. Intern invitations retain their one-year default; no account is marked email-verified merely by provisioning it.

After an authorized Google login resolves a pre-created account, persist the matching Google-verified email for subsequent protected-request checks. Reject email ownership conflicts; never synthesize verification from an invitation or a local session.

Show the signed-in user's first and last name with their permission-derived role (Intern or Doctor/Admin), never the generated internal username. Fill missing names from the authenticated Google profile; preserve names already set by an administrator. Use a neutral account label until a name is available, and label inactive access explicitly.

Use the same identity formatting for allauth account notifications and the homepage, including the post-login success message.

Rejected Google identities lead to a themed, non-cacheable access-denied page at a clean URL, with a CSRF-protected retry and home link. Retrying starts a fresh OAuth flow with Google's account chooser; never replay callback state or relax invitation/verification checks.

Admins preauthorize email addresses with a default calendar-year grant. A verified Google email must match that list. Every submission checks the grant again. Admins can revoke access or extend the expiry for repeat exams; require an administrative reason and retain an audit trail. Doctor access uses explicit permissions and is managed in Django admin. Admin accounts require separate strong credentials; MFA is a production gate.

Camera capture uses getUserMedia over HTTPS, a video preview, and canvas blobs held in memory. No gallery picker or automatic device save. Camera access is user initiated and stopped after use. Browser capture cannot guarantee prevention of screenshots, OS caching, or forged uploads. Unsupported browsers receive an actionable error, no gallery fallback.

Server validates image format, decoded dimensions, request size, image count, and patient quota. Re-encode JPEG with EXIF orientation corrected and metadata removed. Compression must be reviewed by a doctor for diagnostic suitability; maximum 2048-pixel long edge and quality 85 are provisional. Photos are supplementary clinical documentation, not diagnostic imaging.

## Delivery plan and gates

The public database's temporary 14-day branch expiry is removed at the operator's request. Retain Neon Free within its current quotas; no application record-expiry policy is inferred from hosting. SeaweedFS remains an optional self-hosted photo store requiring managed disk/compute, not a replacement for PostgreSQL. Upload success must survive the browser's navigation; fetch submissions return the private confirmation-page destination. Doctor search distinguishes one visit's details/photos from patient-wide comparison, with explicit navigation back to records and home. Historical age is displayed per visit.

After live Drive checks pass, the public preview may enable synthetic visit saving through the private Drive backend. At the operator's request, omit the global preview banner from the interface. Deployment stage and remaining clinical launch gates are documented operationally. Capture counts must update immediately on both add and remove, including zero and singular states.

16 October preview authorization: publish the reviewed code, run GitHub CI, deploy a synthetic-only Render preview and connect records.bulkhead.cc before Drive consent is available. Render defaults to camera preview only: server-side submissions are disabled until external storage is verified and the clinical launch gates pass. Phone camera capture can be tested without persisting photographs. Auto-deploy stays off; releases are manually approved. No real records are imported or submitted in this phase.

Google Drive target: OAuth authorization by the clinic Workspace user (Shared Drives unavailable). A separate Desktop OAuth client runs a localhost-only setup flow; website Google login scopes remain unchanged. Request drive.file plus identity scopes to verify the storage owner. Save refresh credentials only in ignored secrets/host secret files. Create an app-owned private root in My Drive; persist Drive file IDs in photo references. New uploads use the operator-requested descriptive location/patient/visit folders below; existing file references remain valid. Never switch existing filesystem references silently. Live upload/read/delete and private delivery verification are required before enabling this backend for clinical data. External OAuth apps in Testing can issue seven-day Drive refresh tokens; resolve the publishing/account policy before unattended hosting.

Google sign-in shares the clinical application's local CSS, navigation and responsive layout. Display the supplied hospital logo below navigation and the supplied favicon throughout the shared layout. Preserve CSRF-protected POST login and guidance to use an invited account; branding requires no external frontend services.

1. Foundation: remove embedded credentials; portable local settings; models, migrations, grants, private image handling, consent and authorization tests.
2. Workflow: mobile camera capture, submission, doctor comparison, access administration and audit. Gate: automated role/expiry/upload tests plus physical Android Chrome and iPhone Safari checks over HTTPS.
3. Operations: supported dependency versions, GitHub CI, Windows service and reverse-proxy instructions, backup/restore. Gate: production check passes, TLS, OAuth callback configured, MFA, disk alerts, encrypted backups, restore exercise, concurrency/load test.
4. Pilot: synthetic records first, clinician image-quality review, then small authorized cohort. Collect failed capture/upload counts without clinical payloads; iterate based on intern and doctor feedback.

## Hosting and unresolved inputs

The current database target is Neon, AWS Singapore, PostgreSQL 17; both Render and Neon currently lack a Mumbai region. Keep the app and database near each other and measure latency from Gujarat. Public web hosting and private cloud photo storage are still separate deployment work. Free external hosting is not assumed suitable for sensitive patient photographs; evaluate current pricing, region, backups and privacy terms before real records. The user authorized Neon setup below; public clinical deployment still requires the production gates.

Provider subscription details supplied by the user: app.ahmcsrksm.in, plan label Platinum, 2 GB disk allocation, overuse allowed, IIS application pool and ASP.NET enabled, MySQL/MariaDB and MS SQL allocations, remote backups enabled, and 100 MB per mailbox. This is evidence of a Windows hosting subscription, not proof of full dedicated-server access. Python service execution, shell/RDP access, PostgreSQL availability, RAM/CPU limits, extra-disk cost and hard quota enforcement remain unconfirmed. The PostgreSQL quota summary alone does not establish that a PostgreSQL server is available. Confirm runtime and database support before changing the app architecture. At 50 MiB per patient, roughly 38-40 maximum-quota patients would consume the entire 2 GB allowance before application overhead and backups; external or expanded photo storage is needed for a larger rollout. Email remains optional and stores no clinical records.

Need clinic decisions: expected patients/photos per month, available disk and RAM, server OS, domain/DNS, backup destination, lawful retention and consent process, doctor roster, existing records recovery, and whether patient IDs are unique across locations. Delete/retention and account lifecycle must be approved before real data ingestion.

Earlier Plesk discovery: only MariaDB and MSSQL Server were available in the Windows subscription's database-server selector. MariaDB was considered for adaptation but no database switch was implemented. Later Linux SSH connectivity remained unresolved, leading to the current Neon/Render investigation. The bounded terminal/process experiment remains documented in docs/HOSTING_PROBE.md. The clinic account lacks Shared Drives. My Drive OAuth authorization and synthetic upload/read/delete/offline-refresh checks have now passed locally; switching storage and deploying credentials remain pending. Public preview saving is still disabled.

## Neon setup requested 15 October 2026

Configure only Postgres for organization `org-wild-forest-66608257`, project `delicate-wind-71461620`, branch `production`, using the Neon CLI, project-scoped OAuth MCP and Neon agent skills. Preserve Django, psycopg, existing Google authentication and the private file/S3 storage design. `neon deploy` provisions Neon configuration, not the Django web host. Pull connection secrets into ignored local environment files; support DATABASE_URL with TLS and pooled-connection-safe settings. Local shell environment takes precedence over dotenv files. Add an npm build entry that runs the existing Django checks/static collection rather than introducing a new frontend framework. Verify using synthetic records and isolated test databases/branches; never run destructive tests against the production branch. No DNS changes or live clinical web deployment are part of this setup.

## Exit criteria (Neon integration)

CLI linked to the requested IDs/branch; only Postgres declared; MCP configured with OAuth and scoped to this project; npm build succeeds; application starts; live Postgres connectivity and a synthetic application workflow are demonstrated, with exact successes/failures recorded. Preserve the broader production launch gates above.

## Exit criteria (clinical production launch)

Use a same-origin referrer policy in both HTML and response headers: internal POST forms must retain their origin for CSRF verification, while external destinations receive no referrer. Never trust the opaque `null` origin or disable CSRF to work around login errors.

All clinical routes enforce roles; expired/revoked interns fail despite active sessions; unlisted or unverified Google identities fail; consent is server-required; oversized/corrupt/animated files fail; quota cannot race across concurrent uploads; images have no public URL; comparisons never leak to interns; records survive email outages; failure leaves no partial records/files. Production additionally requires the operational gates above. Initial implementation is a development foundation until these gates are demonstrated.

Semester invitations accept an Excel email column, newline/tab/whitespace/comma/semicolon separators, case normalization and duplicate removal. Invalid tokens identify their source line and block the entire submission; no partial grants. The result reports new and existing grant counts; existing expiry/revocation remains unchanged.

## Location folders and six-digit case numbers

New visits accept 1?6 ASCII digits for the case number and store a six-digit zero-padded value (2413 becomes 002413); optional previous case numbers use the same rule. Seven digits, letters and all-zero case numbers are rejected. Search normalizes numeric case numbers while preserving retrieval of legacy identifiers. Existing numeric IDs are normalized by a guarded migration; conflicting normalized identities abort rather than merge.

An unticked optional tf_shift means AnandHospital; ticked means TribhuvandasFoundation. Patient identities and photo quotas are scoped to location and case number, preventing unrelated same-number cases at different sites from merging. Doctor search can filter location; comparison stays within one location-specific patient. Explicit location accompanies links/forms; missing location on older forms defaults to AnandHospital.

Drive layout for new uploads is Location/CaseNumber_Patient-Name_First-Visit-Reason/VisitIndex_Visit-Reason_Intern-Name/random.jpg. The first visit at that location fixes the patient folder label; later changes in name/reason do not create a new patient folder. All name words are retained, whitespace becomes hyphens, and unsafe path punctuation is sanitized. Every word is retained within the existing 200-character field limits; folder labels are bounded accordingly. The per-patient visit index is persisted and allocated under the same patient transaction lock as quota reservation, with a uniqueness constraint. Retries reuse the original visit without allocating another index. Clinical names/reasons are intentionally present only in private Drive folder names, at the operator's request; browser URLs, logs and photo references remain opaque. Existing photos/folders are not moved.

With drive.file authorization, manually created location folders may be invisible to this app. The app creates managed location folders inside its existing private root. Do not silently expand OAuth scopes. Preconfigured location-folder IDs avoid per-request location-folder creation; otherwise folder races are serialized across patients in the same location; rollback removes uploaded files while empty folders remain for reconciliation. Existing root permissions remain private.

## Reliable visit-save feedback

Successful submissions navigate to a dedicated private confirmation page showing the saved visit's patient name and actual persisted image count. This replaces the fleeting homepage notification. Confirmation URLs use opaque submission UUIDs, never patient identifiers; no names are stored in flash cookies, URL parameters or browser storage. Only the original uploader with currently active submission access may view the confirmation. Repeated page loads remain clear, and replayed uploads resolve to the same confirmation and original photo count.

The form shows a visible saving state and scrolls/focuses errors into view. Unconfirmed network/server responses show plain-language retry instructions, retain the photo queue and submission UUID, and never expose exception details. Validation errors remain actionable. Failed saves do not navigate or show success; malformed JSON or unexpected redirects cannot produce false confirmation.

The save service itself rejects empty photo queues/empty photo payloads before creating records, in addition to HTTP upload validation. A partial upload failure rolls back the entire visit and removes files uploaded earlier in that attempt.

When an eleventh photo is attempted, keep the ten existing captures and bring the limit message above the image queue into view with smooth scrolling and keyboard focus. Removing a capture restores the live count and permits another capture.
