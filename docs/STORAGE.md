# Storage decision

The retrieval index belongs in PostgreSQL. Patients have a unique clinic ID; visits retain OPD, case year, diagnosis, uploader, consent, timestamps and photo references. OPD and case-year columns are indexed. The doctor portal searches these records, then presents dated images for comparison. Selecting a storage vendor does not itself provide clinical search.

| Option | Fit | Decision |
| --- | --- | --- |
| PostgreSQL + private server files | Existing Windows server, few services, easy inspection | Default first rollout pending capacity and backup confirmation |
| PostgreSQL + SeaweedFS S3 endpoint | Self-hosted object storage and future independent storage scaling | Candidate if S3 is wanted from day one; deployment needs a separate integration/security pilot |
| MinIO community | Familiar S3 API, but upstream community repository is archived and marked unmaintained | Avoid for a new clinical deployment |
| lakeFS | Version control over underlying object storage | Defer; adds a service and does not replace the underlying store |
| PostgreSQL bytea/large objects | Binary data supported, can place records and images in one database | Possible for modest volume; increases database backup/WAL and restore load, so keep photos separate initially |
| Clinic-owned Google Workspace Shared Drive | Potentially useful if the clinic already has pooled storage and administrative control | Candidate private API-backed photo store; custom integration and operational validation required |

Sources checked October 2026: [MinIO repository](https://github.com/minio/minio), [lakeFS internals](https://docs.lakefs.io/concepts/internals/), [SeaweedFS](https://github.com/seaweedfs/seaweedfs), [PostgreSQL binary storage](https://jdbc.postgresql.org/documentation/binary-data/), [django-storages S3 configuration](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html).

## Google Workspace candidate

The user proposed Google Workspace Drive to keep photos off the 2 GB hosting subscription. Google lists Business Standard at 2 TB and Business Plus at 5 TB per licensed user in organization-wide pooled storage; this pool is also consumed by other Workspace data. Confirm the clinic's actual edition, available pool, Shared Drive capabilities and administrator approval before purchasing anything or connecting real records. See [Google's storage limits](https://knowledge.workspace.google.com/admin/drive/storage-and-upload-limits-for-google-workspace).

Use an organization-owned private Shared Drive, with a narrowly authorized backend identity and no intern membership or public sharing. Service accounts cannot own files and have no personal storage quota: Shared Drive uploads or human-user OAuth authorization are required. Prefer Shared Drive access without broad domain-wide delegation where organization policy permits. See [Drive Shared Drive guidance](https://developers.google.com/workspace/drive/api/guides/about-shareddrives).

The intended flow is camera -> validation/compression -> private Drive API upload -> database record containing an opaque Drive file ID. Doctors still search the database; authenticated photo routes fetch images from Drive. Use opaque filenames without patient names/diagnoses. Never embed public Drive links, ask interns to connect their personal Drive, or depend on the patient's ID appearing in the Drive filename.

Drive is not an S3 backend. The selected account lacks Shared Drives, so an OAuth-authorized My Drive backend and loopback setup command have now been implemented. They remain disabled and unconnected pending credentials and live verification. See [setup instructions](GOOGLE_DRIVE_SETUP.md). Hard-crash reconciliation, lifecycle alerts and backup/restore remain launch gates. API availability and latency affect comparisons; being hosted in India does not establish that Drive data is stored locally. Administrative deletions, retention and independent recovery must be addressed; pooled storage is not itself a backup. See [Drive API limits](https://developers.google.com/workspace/drive/api/guides/limits).

## Optional S3 backend

The application supports `PHOTO_STORAGE=s3`, using a private S3-compatible endpoint through django-storages. Set `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and `S3_REGION_NAME`. Credentials should have access only to the clinical bucket. Use TLS, enforce private bucket policy, block public anonymous access, and restrict the endpoint to the application network. Never expose filer/volume/admin ports directly to the internet.

The application streams images through `/photos/<opaque-uuid>/` after checking doctor permission; its storage classes deliberately reject `.url` calls. The S3 backend setting is implemented but has not been exercised against a real object-store server. Before use: test write/read/delete, anonymous denial, metadata stripping, TLS, backup recovery, endpoint outages and rollback cleanup. Setting a backend does not move existing photos: perform an offline copy and manifest verification before switching an existing installation.

## Capacity and consistency

Provisional compressed quota is 50 MiB per patient across all visits, 10 photos per visit, 10 MiB per incoming image and 25 MiB total upload. Browser capture resizes to 2048 pixels at JPEG quality 90; server independently validates and re-encodes at quality 85, removes metadata and enforces decoded dimensions. Get clinician approval for image quality before real use.

At the quota maximum, 1,000 patients represent approximately 49 GiB of photos before backups, filesystem overhead, temporary buffers and database space. Actual usage depends on capture counts and image complexity. Reserve headroom and alert at 70/85/95% disk usage. Open-source software does not eliminate hardware, backup or administration cost.

The supplied Plesk subscription allocates only 2 GB: approximately 38-40 patients at the 50 MiB maximum would consume all of it, with no room for application dependencies, logs, databases or backups. Fewer full-quota patients fit in practice. Overuse permission does not establish extra capacity, absence of charges or filesystem hard-quota behavior. Confirm those details with the provider. Self-hosting SeaweedFS on the same allocation does not increase available space; expanded private disk or an independently provisioned private object store is the likely requirement for a meaningful rollout.

Quota reservation uses an atomic conditional database update so parallel submissions cannot consume the same remaining allowance. Submission IDs make retries idempotent. Ordinary transaction failure deletes files already written; database transactions do not atomically include a filesystem/object store. A hard crash can leave orphan objects: reconcile manifests and quota counters on a controlled schedule before launch. Do not automatically delete files without an reviewed retention policy.

Back up database and image store as one consistent set: pause submissions or take coordinated snapshots, retain a manifest with object keys/sizes/checksums, encrypt backups off-server and perform a restore exercise. S3 replication on one server is not an independent backup.
