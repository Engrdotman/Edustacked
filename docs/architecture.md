# Architecture

## Application shape

The system is a modular monolith: one Django deployment and relational database, divided into Django apps by business responsibility. This keeps local development and transactional workflows straightforward while leaving boundaries clear enough to evolve modules independently if real scaling needs arise. Do not introduce microservices or future domain apps before they are needed.

The React/Vite frontend owns presentation, navigation, and user interaction. It is not a security boundary and must not make authorization decisions. The Django REST Framework backend owns validation, business rules, persistence, authentication, authorization, and tenant isolation. The frontend calls backend resources over JSON REST APIs; its API base URL is supplied using `VITE_API_BASE_URL`.

## Initial backend boundaries

- `core`: shared infrastructure and foundational endpoints such as the health check.
- `accounts`: custom user model based on Django `AbstractUser`; no custom login or registration API is part of this module.
- `schools`: school tenant identity and user-school memberships.

## Tenancy and data isolation

Use a shared database and shared schema. Local development defaults to SQLite for a low-friction setup; deployment uses PostgreSQL selected explicitly through environment variables. SQLite is rejected when `DJANGO_DEBUG=false`. Each school-owned record added in later modules must have an explicit school relationship. For every request that accesses school data, the backend must:

1. Authenticate the user using the configured authentication mechanism.
2. Resolve the requested school only through an active membership belonging to that user.
3. Apply the authorized school to the query itself and to create/update validation; never treat a frontend-provided `school_id` as proof of access.
4. Deny access when membership is missing or inactive, and avoid leaking whether another tenant's record exists.

`apps.schools.tenancy.SchoolScopedQuerySetMixin` is the reusable base for tenant-owned DRF generic views. Set its school URL kwarg and lookup field when needed, keep the model's school foreign key in the queryset, and include the mixin before the DRF generic view class. It resolves a URL `school_id` or `X-School-ID` through the authenticated user's active membership, scopes `get_queryset()` (therefore list and object retrieval), and forces the authorized school on create/update. A client-supplied identifier is context only, never authorization. Missing or unauthorized tenant context returns a uniform 404. A serializer should not permit a client to set a tenant relationship as proof of authorization.

For every future tenant-owned model, add a non-null school foreign key with an appropriate deletion policy and indexes based on real query patterns. For every endpoint, authenticate the user, resolve an active membership, apply the school in queryset and write validation, and avoid error messages that reveal other tenants. Do not add broad permissions as a shortcut. Each tenant-owned API must include automated tests proving same-tenant access and denied cross-tenant reads/writes, including missing and invalid tenant context. These tests are a release requirement for future data modules.

## Database strategy and integrity

SQLite is the default for local development. PostgreSQL is configured for deployment through `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE`, and `DB_CONNECT_TIMEOUT`; credentials belong in the deployment secret manager, never source control. Use migrations for schema changes and do not make destructive database changes as part of setup. The current schema and constraints are documented in [database-schema.md](database-schema.md); migrations are the executable source of truth.

Use foreign keys, explicit uniqueness constraints, and validation for invariants that must hold under concurrent requests. Add indexes only for demonstrated lookup patterns; unique fields and relationship fields already receive appropriate database support. Use database transactions for future multi-record workflows and credit deductions.

## Authentication and authorization

The custom `accounts.User` extends `AbstractUser`. The normalized `login_email` is the unique email API identity; the existing `username` and `email` fields are retained for compatibility. Migrations backfill `login_email` only for unambiguous existing addresses and do not remove or rewrite user records. Passwords use Django's configured password hashers and validators.

Authentication uses Simple JWT with five-minute access tokens and seven-day refresh tokens by default. Access tokens are returned to the frontend and kept in memory only. Refresh tokens are rotated, stored in an HttpOnly cookie, and blacklisted on rotation/logout; password changes revoke outstanding refresh tokens and invalidate password-hash-bound access tokens. Cookie security, CORS credentials, and CSRF protection are configured for browser clients. Logout cannot immediately revoke an already-issued access token; its short lifetime bounds that window. See [authentication-and-rbac.md](authentication-and-rbac.md) for endpoints and operational setup.

Platform superadmins are Django `is_superuser` accounts and are separate from school roles. School roles live on `SchoolMembership`; `apps.schools.permissions.HasSchoolPermission` checks active membership and a role permission map on every request. No business workflows are included in this module. The current school primary key is Django's unique auto-incrementing identifier; it is retained to avoid a destructive primary-key conversion.

The versioned API uses URL paths under `/api/v1/`. Public endpoints include health checks, CSRF token bootstrap, login, refresh, logout, and password reset. Profile, membership, school selection, password change, school creation, and membership provisioning are authenticated and permission-checked. The database health endpoint returns a generic 503 response when the selected database is unavailable.

## Report-card credits and billing extension point

Billing is not implemented in Module 1. Later, report-card finalization should atomically consume one credit per student/term finalization and create an immutable usage-ledger entry tied to the finalized report/version and school. A uniqueness/idempotency rule must ensure retries do not charge twice. Preview, download, and reprint of an already finalized report must not consume more credits. Credit packages, balances, payment integration, and webhook processing should be separate later module concerns; external payment notifications must be verified and processed idempotently.

## Security and deployment

Keep secrets in environment variables or a secret manager; commit only `.env.example` files. Disable debug in production, set explicit allowed hosts and HTTPS/security headers, restrict CORS to trusted origins, and use PostgreSQL backups and monitored migrations. Production mode enables HTTPS redirects, secure session/CSRF cookies, content-type protection, clickjacking protection, and a one-year HSTS policy. HSTS subdomains and preload are opt-in because they require every covered host to remain HTTPS-only; Django's `check --deploy` will warn until operators confirm and enable them. Apply least privilege to database/application credentials, validate API input on the backend, protect state-changing requests according to the chosen authentication mechanism, rate-limit sensitive endpoints when introduced, and avoid logging credentials or sensitive student data. Production deployment and security hardening remain later roadmap work.
