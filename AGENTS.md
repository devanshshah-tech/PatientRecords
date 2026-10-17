# Engineering rules

Read SPEC.md before changing behavior. Treat patient identifiers, diagnoses, photographs, account lists, and credentials as confidential. Never print secrets, commit environment files, or use real patient data in tests.

Work in reviewable increments: document intent, implement, run relevant tests, report evidence and remaining limitations. Keep SPEC.md and implementation aligned. Use skills when they materially help; avoid unnecessary infrastructure or agent delegation.

Authorization is enforced on every protected request, including image delivery. Interns may submit only during an active grant; doctors require explicit Django permissions. Staff status alone is not clinical authorization. Expiry and revocation must affect existing sessions immediately.

Images are private, never served through a public media route. Validate content and quotas on the server, strip metadata, and clean up files after failed transactions. Never attach clinical images to email. Avoid patient information in logs, URLs, or third-party frontend services.

Before merging: run Django checks, migrations consistency checks, and tests for authorization, expiry, consent, upload validation, and privacy. Before production: supported dependencies, HTTPS, production security checks, disk capacity, restricted filesystem ACLs, encrypted backup and a demonstrated restore. Never deploy or import real records without the deployment gates in SPEC.md.

CI on GitHub Free uses synthetic data and no production credentials. Deployment is manually approved after verification. Record failures and fixes in the change report; add regression coverage for security defects.
