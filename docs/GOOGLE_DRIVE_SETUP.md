# Clinic My Drive OAuth storage

Status: clinic OAuth authorization completed locally. Real API synthetic upload, exact read-back, deletion and offline token refresh passed. Deploy credentials through a Render secret file and verify the full synthetic web workflow before using that deployment. Website Google sign-in remains separate; clinical launch requires the documented operational gates.

## Account setup

1. In Google Cloud, select the storage project's Google Auth Platform configuration. Enable **Google Drive API** under APIs & Services → Library.
2. If the app is External/Testing, add the clinic storage owner's email as a test user. The Workspace administrator may also need to allow the app.
3. Add `https://www.googleapis.com/auth/drive.file` to Data Access. The setup flow also requests OpenID/email to confirm the exact storage owner. Do not request full-drive scope.
4. Create an OAuth client of type **Desktop app**, named Clinical Records Storage Setup. Keep the existing website Web application client unchanged.
5. Download its JSON to the ignored project path `.secrets/drive-client.json`. Do not send JSON, authorization codes or refresh tokens in chat. Restrict this directory's Windows ACL to the operator; deployed secret files must be readable only by the service identity.

## Authorize locally

From the project root, using the existing virtual environment:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe manage.py connect_drive --expected-email YOUR-CLINIC-STORAGE-EMAIL
```

The command opens a browser and binds a temporary callback to the loopback interface. Select the clinic Workspace account. It checks verified ownership, requests offline access, creates an app-owned private Clinical Records folder, and saves credentials to `.secrets/drive-token.json`. It writes `DRIVE_CREDENTIALS_FILE` and `DRIVE_ROOT_FOLDER_ID` into ignored `.env.local`, leaving `PHOTO_STORAGE` unchanged. No desktop callback is added to the website Web client's redirect URIs. Existing token files are not overwritten; reconnect/rotate explicitly with the operator rather than deleting an active token.

Then run:

```powershell
.venv\Scripts\python.exe manage.py verify_drive
```

This uploads a synthetic JPEG, reads it back byte-for-byte, then deletes the synthetic file. Empty synthetic folders remain visible for reconciliation. It neither tests real clinical records nor proves the entire web flow against Drive. Next test synthetic upload and authorized doctor delivery through the app, plus retry/failure cleanup.

## Activation and migration

Do not change `PHOTO_STORAGE=drive` until credentials and synthetic verification pass. Existing filesystem/S3 photo references cannot be read by the Drive backend. Inventory existing synthetic photos and explicitly migrate them or start an isolated clean pilot database; never delete records or switch backends silently. An existing clinical dataset needs a migration with checksums, rollback and coordinated backups.

At the operator's request, new uploads use private descriptive location/patient/visit folders and random JPEG names, and return short `drive/<file-id>` references, limits upload/download memory, rejects public URLs, and uses preallocated file IDs for cleanup after ambiguous upload failure. Root/folder creation and database transactions are not atomic with Drive. Hard crashes, failed cleanup and empty folders require reconciliation; this and a tested recovery workflow remain production gates. Current synchronous reads/writes hold requests open during network I/O; load-test before a real cohort.

In Render, mount the authorized-user JSON as a secret file, set `DRIVE_CREDENTIALS_FILE` to its host path, and set `DRIVE_ROOT_FOLDER_ID` through secret environment settings. Never commit or upload `.env.local` as a production config.

## Refresh token lifecycle

Google can issue seven-day refresh tokens when an External OAuth app is in Testing and requests Drive scopes. This is unsuitable for unattended production storage. Resolve the app's publishing status or approved internal Workspace configuration before hosting; reauthorize if needed. Revocation, administrator policy and account changes can still interrupt refresh access. Alert on storage failures and document reconnection. `drive.file` does not grant the app blanket access to all existing mailbox/Drive data and is not a folder sandbox for all future grants; keep this integration limited to app-created files.

Sources: [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline access and token expiry](https://developers.google.com/identity/protocols/oauth2), [file uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads).

## Location folders

Run `python manage.py prepare_drive_locations` after storage authorization. This verifies the app root is unshared, creates/reuses app-visible `AnandHospital` and `TribhuvandasFoundation` children, and writes `DRIVE_ANAND_FOLDER_ID` and `DRIVE_TF_FOLDER_ID` to ignored `.env.local`. Configure the same IDs on the host. `drive.file` cannot necessarily see folders created manually in My Drive; those remain untouched. No broader Drive scope is needed. Run setup once per root; do not run concurrent setup processes.

Unticked shift is Anand Hospital; ticked is Tribhuvandas Foundation. The layout is `Location/002413_Synthetic-Patient_First-Reason/1_First-Reason_Synthetic-Intern/random.jpg`. Reasons come from the visit reason/diagnosis field. First-visit naming is retained on follow-ups, and numbering is per location-specific patient. Spaces in any number of words become hyphens; unsafe path punctuation becomes hyphens too. Existing 200-character field limits still apply. Names/reasons are now deliberately visible to the clinic account inside private Drive folders; browser image URLs and database photo references remain opaque. Restrict root sharing accordingly. Existing opaque folders and stored Drive file IDs are not renamed or moved.

Patients are matched by location plus padded case number. The same case number at different sites never merges patients automatically. The migration normalizes legacy numeric IDs and backfills visit indices, aborting on any collision. It preserves nonnumeric legacy IDs for doctor retrieval, existing photos, account grants and audit history. Backing out the location schema after new duplicate case numbers exist across sites requires a reviewed data plan; do not blindly roll migrations backwards.


## OAuth branding and public URLs

Use Patient Records as the OAuth app name, matching the public homepage. Set homepage to https://records.bulkhead.cc/ and privacy policy to https://records.bulkhead.cc/privacy/; /health/ is not a policy. Verify bulkhead.cc as a Search Console Domain property with the exact TXT challenge for the Google account managing the OAuth project. Keep the TXT record and observe any Google-requested 24-hour delay after verification before retrying branding review. Both public URLs must be reachable over valid HTTPS without login. Review privacy wording with the clinic, particularly contact and retention practices. Publishing branding and switching Audience to production are separate actions; neither restores an expired refresh token. Reconnect with the existing OAuth client and preserve root/location/file IDs after publication.
