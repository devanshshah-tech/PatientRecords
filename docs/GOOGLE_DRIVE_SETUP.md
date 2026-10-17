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

The backend creates opaque patient/visit folders and JPEG names, returns short `drive/<file-id>` references, limits upload/download memory, rejects public URLs, and uses preallocated file IDs for cleanup after ambiguous upload failure. Root/folder creation and database transactions are not atomic with Drive. Hard crashes, failed cleanup and empty folders require reconciliation; this and a tested recovery workflow remain production gates. Current synchronous reads/writes hold requests open during network I/O; load-test before a real cohort.

In Render, mount the authorized-user JSON as a secret file, set `DRIVE_CREDENTIALS_FILE` to its host path, and set `DRIVE_ROOT_FOLDER_ID` through secret environment settings. Never commit or upload `.env.local` as a production config.

## Refresh token lifecycle

Google can issue seven-day refresh tokens when an External OAuth app is in Testing and requests Drive scopes. This is unsuitable for unattended production storage. Resolve the app's publishing status or approved internal Workspace configuration before hosting; reauthorize if needed. Revocation, administrator policy and account changes can still interrupt refresh access. Alert on storage failures and document reconnection. `drive.file` does not grant the app blanket access to all existing mailbox/Drive data and is not a folder sandbox for all future grants; keep this integration limited to app-created files.

Sources: [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline access and token expiry](https://developers.google.com/identity/protocols/oauth2), [file uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads).
