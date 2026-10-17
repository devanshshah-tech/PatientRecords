# Render preview release

The public preview is authorized for synthetic testing before Drive consent. It uses a separate schema-only Neon database (`render-preview`), expiring after 14 days, and contains no copied patient records. Renew or replace it explicitly before expiry. The local production-linked environment remains unchanged.

`render.yaml` describes the free Singapore Python service with manual deploys. Its defaults disable saving server-side even if JavaScript is bypassed. After Drive authorization and storage verification, the existing service may override `PHOTO_STORAGE=drive` and `CLINICAL_UPLOADS_ENABLED=true` for synthetic visit tests. `PREVIEW_MODE=true` continues to display testing guidance, with storage availability reflected accurately. Do not photograph patients or enter their details before clinical launch gates pass.

The service binds to Render's assigned PORT on 0.0.0.0 and trusts only the forwarded HTTPS scheme from its managed reverse proxy. Do not enable TRUST_HTTPS_PROXY on a directly exposed server. `/health/` reports HTTP readiness only, not database or storage health. Start-up applies migrations through the direct database connection; requests use the pooled connection.

Credentials are supplied through Render secret configuration, never GitHub Actions. CLI provisioning can upload a separate `.env` secret file containing only reviewed preview settings and the preview URLs, with dotenv explicitly enabled. The Blueprint instead uses Render environment variables, with dotenv disabled. Never upload the local development `.env.local`.

After GitHub checks pass, deploy the release branch manually. Verify HTTPS, no redirect loops, static logo/favicon/CSS, Google redirects, and blocked uploads. Add both the Render HTTPS callback and `https://records.bulkhead.cc/accounts/google/login/callback/` to the website's Google Web OAuth client before testing sign-in.

For the custom domain: register records.bulkhead.cc on the Render service, then create a Cloudflare DNS-only CNAME named records targeting the assigned service.onrender.com hostname. Do not modify unrelated root/mail records. Wait for Render domain verification and its TLS certificate. Proxying can be evaluated after the direct HTTPS setup works.

On Android Chrome and iPhone Safari: test allowed/denied camera permissions, rear camera selection, capture/remove, screen rotation, tab backgrounding and revisiting. Use objects only. Record browser/OS version and failures without account names or clinical payloads. A completed phone check does not prove Drive persistence; run the real storage workflow later.

Drive authorization, tested upload/read/delete, offline refresh, existing-photo migration, backups/restore, MFA, rate limits, storage alerts, retention rules and clinician approval remain required before clinical launch. Disabling preview mode is a separate manually approved release after these gates; do not enable filesystem uploads on the free ephemeral service.
