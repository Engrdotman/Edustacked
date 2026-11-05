# EDUstacked Railway and Paystack Readiness Audit

**Audit date:** 2026-11-04
**Scope:** Phase 1 inspection only. This document is new; application source, migrations, credentials, databases, and hosting resources were not changed.

## Executive summary

The project is a Django REST API and React/Vite single-page application. It already supports a single shared PostgreSQL database with school-scoped records, and Paystack checkout for report-card credits is implemented. The existing GitHub production workflow builds/tests a release package; it explicitly does not deploy to a hosting provider.

Railway deployment is not ready as-is: there is no Railway, Procfile, or Docker configuration; Gunicorn and WhiteNoise are absent; production uploads use local `MEDIA_ROOT`; and service-specific deployment commands/secrets have not been configured. A frontend can remain on Vercel and call Railway through `VITE_API_BASE_URL`.

Paystack is not wholly missing. Report-card credits have initialization, verification, signed webhook handling, server-side price lookup, tenant scoping, and an immutable ledger. Paystack checkout does **not** yet sell/activate the separately priced Offline CBT entitlements. The webhook also does not persist raw webhook event records or independently call Paystack verification before fulfilling a signed `charge.success` event. These are specific follow-up decisions/implementation gaps, not reasons to duplicate the existing credit system.

## 1. Existing architecture

| Area | Finding | Source locations |
|---|---|---|
| Django project | Django 5.2, DRF, custom `config` package; WSGI entry point is `config.wsgi:application`. App code is in `backend/apps/`. | `backend/config/{settings.py,wsgi.py,urls.py}`, `backend/apps/*` |
| React frontend | React 19 + Vite 6 SPA; build output is Vite `dist`; browser API base is `VITE_API_BASE_URL`. | `frontend/package.json`, `frontend/vite.config.js`, `frontend/src/` |
| REST API | Versioned `/api/v1/` endpoints, split by Django app and included in `config/urls.py`. | `backend/config/urls.py`, each app's `urls.py` |
| Authentication | Custom Django `accounts.User`, email login, JWT access tokens, rotating/blacklisted refresh tokens in HttpOnly cookie, email verification/reset flows. | `backend/apps/accounts/`, `backend/config/settings.py`, `docs/authentication-and-rbac.md` |
| Authorization | Central role/capability checks through school membership and permission classes; staff/teachers receive scoped access. | `backend/apps/schools/permissions.py`, `tenancy.py`, app `permissions.py` files |
| Tenancy | Shared-schema tenancy. Every school has one `School` row; users join schools through `SchoolMembership`; tenant-owned records include a school FK and requests resolve the selected school against active membership. No per-school database/schema package is present. | `backend/apps/schools/models.py`, `tenancy.py`, `docs/architecture.md` |
| Database | Exactly one Django `default` database. `DATABASE_URL=postgresql://...` configures PostgreSQL; `psycopg[binary]` is already required. Production (`DEBUG=False`) rejects SQLite. Local development defaults to SQLite. | `backend/config/settings.py`, `backend/requirements.txt`, `.github/workflows/*` |
| School and academic records | School/settings/membership, sessions/terms/classes/arms/subjects/grading, students/enrollments, staff/teaching assignments, attendance, assessments/results are implemented as separate apps. | `backend/apps/{schools,academics,students,staff,attendance,results}/` |
| Report cards | Revisioned workflow `draft → review → approved → finalized`; approved finalization is transactional and consumes one credit on the first publication for a student/term. Preview/PDF retrieval does not consume another credit. | `backend/apps/report_cards/`, `backend/apps/billing/services.py`, `docs/report-cards.md`, `docs/billing-and-credits.md` |
| CBT | Central CBT app owns questions, exams, assignments, sync, results; separately deployed school-local CBT Django service uses SQLite and has its own student UI. Offline CBT entitlements and signed licenses exist. | `backend/apps/cbt/`, `backend/apps/entitlements/`, `local_cbt_server/`, `docs/offline-cbt-phase-6-production-readiness.md` |
| Background work | No Celery, Redis, or central background worker configuration found. Local CBT has a separate `sync_outbox` management command, which is for the school-local service. | `backend/config/settings.py`, `local_cbt_server/offline_exam/management/commands/` |
| Tests/CI | Django app tests, PostgreSQL-backed GitHub Actions jobs, frontend production build. The repo's CI/CD docs describe GitHub workflows; no Railway integration exists. | `backend/apps/*/tests.py`, `.github/workflows/`, `docs/CI-CD-SETUP.md` |

### Database / tenant relationship

Railway PostgreSQL should be one shared database for the central SaaS. `School` is the tenant root, `SchoolMembership` links global user accounts to schools, and business data is isolated by school foreign keys and authorized querysets. Do not create one Railway database per school. The school-local offline CBT service is a separate product component with its own SQLite database; it is not a central tenant database.

## 2. Existing Paystack and billing functionality

The existing `apps.billing` module is specifically the report-card credit purchase system:

- `CreditPackage` stores server-side package credit quantity and price in kobo.
- `CreditPayment` stores unique provider reference, school, package snapshot, amount, currency, payer, and payment state.
- `CreditAccount` plus append-only `CreditTransaction` form the school credit balance and ledger.
- `ReportCardBilling` ensures one credit is charged for the student's first finalized report card per academic term.
- `ReconciliationIssue` supports payment mismatch, refund/reversal, and disputes without silently deleting ledger entries.
- `POST /api/v1/billing/purchases/` authenticates the school user, selects an active package, calculates price on the server, stores a pending payment, and initializes Paystack in NGN/kobo.
- `POST /api/v1/billing/payments/{reference}/` verifies pending checkout with Paystack; the browser callback itself does not grant credit.
- `POST /api/v1/billing/paystack/webhook/` checks HMAC-SHA512 against the raw request body and the server-only Paystack secret, then checks reference/status/amount/currency before fulfillment.
- Payment and wallet updates use row locks/transactions; the unique credit-ledger reference and successful-payment state make repeated success fulfillment idempotent.
- Billing APIs scope payment, balance, and ledger history to the school resolved from the authenticated user's active membership.
- Tests in `backend/apps/billing/tests.py` mock provider requests and cover successful/failed verification, webhook signatures/replay, tenant/role scope, and credit finalization behavior.

Relevant files: `backend/apps/billing/{models.py,providers.py,services.py,views.py,serializers.py,urls.py,tests.py}` and `frontend/src/pages/BillingPage.jsx`.

### Payment gaps and architecture risks

1. The webhook has no durable `PaymentWebhookEvent`/provider-event archive. Duplicate success is safe for the credit ledger, but operators cannot inspect an immutable record of every received event/body and processing outcome.
2. A signed webhook success payload is checked against the local order, but webhook handling does not make a separate Paystack verification API call before granting credit. Choose one fulfillment policy and test it consistently (signature-verified payload validation or an additional server-side verification request).
3. `ServicePlan` and school-scoped `ServiceEntitlement` already exist in `apps.entitlements`; plan prices are in kobo and entitlements create signed Offline CBT licenses. However, there is no school-initiated Paystack purchase endpoint for those plans. Platform superadmins grant entitlements through `POST /api/v1/platform/services/entitlements/` today.
4. CBT service purchases must not be credited to `CreditAccount`. Add a distinct purchase/fulfillment relationship to `ServiceEntitlement`, or a generic payment order with explicit product type and separate fulfillment handlers. Preserve report-card `CreditTransaction` exclusively for report-card credits.
5. There is no subscription requirement in the current model; keep service plan purchase/license durations distinct from compulsory recurring subscriptions.
6. `PAYSTACK_MODE` and `PAYSTACK_PUBLIC_KEY` are requested in the brief but are not consumed by backend settings. The current provider chooses test/live behavior based on which secret key is configured. A frontend public key integration does not appear necessary for hosted Paystack Checkout; do not expose secret credentials.

## 3. Railway deployment readiness

### Already available

- Production settings guard against the default insecure secret and reject SQLite when `DJANGO_DEBUG` is false.
- `DATABASE_URL` PostgreSQL parsing, psycopg driver, database connection timeout/lifetime settings are present.
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, secure cookies, HTTPS redirect, proxy SSL header, and HSTS controls exist.
- `collectstatic` paths are configured (`STATIC_ROOT=backend/staticfiles`); `/api/v1/health/` and `/api/v1/health/database/` endpoints exist.
- Structured console logging is configured.
- Migrations are standard Django migrations.
- Vercel can host the frontend independently; `VITE_API_BASE_URL` needs the public Railway API base URL, including `/api` as expected by `frontend/src/services/api.js`.

### Missing or not configured

- No `railway.toml`, `Procfile`, Dockerfile, or Railway service setup is present.
- `gunicorn` is absent from `backend/requirements.txt`. A production WSGI server and start command must be added/configured.
- WhiteNoise is absent. `collectstatic` alone does not make Django admin/static assets available. Add a static-file serving strategy (WhiteNoise is suitable for app static files) or equivalent.
- `MEDIA_ROOT=backend/media` is local disk. Railway service filesystems are not an appropriate durable media store. School logos, principal signatures, student/staff photos, and CBT uploads require durable private object storage plus backups. Keep tenant-authorized file views; do not publish private media as an unrestricted bucket.
- No explicit Railway migration/release command or Railway health-check path is configured. Migrations need a single controlled pre-deploy/release invocation; avoid every web worker racing migrations on startup.
- No Railway backups/restore evidence, DB connection sizing, alerting/error monitoring, or production Postgres rehearsal is present in this repository.
- The existing `.github/workflows/deploy-production.yml` is not a Railway deployment workflow: after tests it runs migration/static collection using GitHub secrets and publishes a downloadable release package. Its own body says no hosting provider is configured. Do not treat its successful run as proof that Railway is updated. Review/retire its production `DATABASE_URL` migration step when introducing Railway, to avoid unintended migrations from two deployment paths.
- Vercel and Railway must be configured with matching exact origins: Vercel origin in backend CORS and CSRF trusted origins; Railway API base in Vercel's `VITE_API_BASE_URL`. Since the refresh token is an HttpOnly cookie, choose frontend/API domains and cookie SameSite/credentials settings that work together and verify browser login/refresh/logout in production domains.

### Recommended first Railway layout

1. One Railway PostgreSQL service for the central application.
2. One Railway Django web service rooted at `backend/` (or a Docker build context that installs `backend/requirements.txt`), with `config.wsgi:application` served by Gunicorn and bound to Railway's `$PORT`.
3. Keep React static hosting on Vercel initially. Set Vercel's `VITE_API_BASE_URL` to `https://<api-domain>/api` and add the exact Vercel origin to the backend CORS and CSRF environment values.
4. Add migrations as a single Railway pre-deploy/release command, then configure the database-backed health endpoint `/api/v1/health/database/` for deployment health checks. Do not create a second central DB per school.
5. Add private durable object storage for user uploads before pilot schools upload real records.
6. Do not add Redis/Celery until an actual asynchronous job requires them. Existing offline CBT local sync worker stays on the school server, not Railway.

## 4. Environment variables for a Railway central backend

Set these in Railway's secret/environment settings, not in source control. Values below are names and descriptions only.

| Variable | Required value/use |
|---|---|
| `DJANGO_SECRET_KEY` | Long random production-only Django/JWT secret; distinct from local/test keys. |
| `DJANGO_DEBUG` | `false`. |
| `DATABASE_URL` | Railway private PostgreSQL connection reference, not a public DB URL. The code parses PostgreSQL URLs. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated exact Railway API domain(s), no wildcard. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Exact HTTPS Vercel/custom frontend origins, comma separated. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact HTTPS frontend/API origins as applicable, comma separated. |
| `FRONTEND_BASE_URL` | HTTPS frontend origin; used to construct the Paystack callback. This is the setting name in code; `FRONTEND_URL` is not read. |
| `PAYSTACK_SECRET_KEY` | Paystack **test** secret key for test mode; later use the live key only in production after test sign-off. Server only. |
| `EMAIL_BACKEND` | SMTP backend (default in production). |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP service configuration for verification/reset emails. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | Select the provider's required transport; never both true. |
| `DEFAULT_FROM_EMAIL` | Verified sender identity, e.g. EDUstacked's configured sender. |
| `CBT_LICENSE_SIGNING_KEY`, `CBT_PACKAGE_SIGNING_KEY` | Stable random signing secrets, separately protected; coordinate with local CBT servers. Rotating invalidates signatures unless coordinated. |
| `CBT_OFFLINE_GRACE_DAYS` | Central policy from 0 to 90; defaults to 7. |
| `DB_CONN_MAX_AGE`, `DB_CONNECT_TIMEOUT` | Tune for Railway Postgres/proxy connection limits. |
| `DJANGO_SECURE_HSTS_SECONDS` | Set after HTTPS/domain validation; current production default is one year. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SECURE_HSTS_PRELOAD` | Leave false until all covered domains are permanently HTTPS-ready. |
| `AUTH_REFRESH_COOKIE_DOMAIN` | Optional shared parent domain only if frontend/API cookie topology requires it; validate cookie behavior first. |
| `DJANGO_LOG_LEVEL` | Usually `INFO`; send console logs to Railway and an error monitoring service. |
| Object storage variables | Not currently implemented/standardized; add only after selecting a private object-storage provider and Django storage integration. |

`PAYSTACK_PUBLIC_KEY`, `PAYSTACK_MODE`, and `FRONTEND_URL` are not read by current backend code. Keep Paystack test/live choice controlled by the server-side secret until explicit mode handling is designed.

## 5. Data and feature models to reuse or extend

| Need | Existing model(s) | Follow-up |
|---|---|---|
| School tenant / owner | `School`, `SchoolMembership`, `User` | Reuse; do not introduce a parallel tenant model. |
| Sessions/terms | `AcademicSession`, `Term` | Reuse. |
| Students and enrollment | `Student`, `StudentEnrollment` | Reuse. |
| Report card workflow | `ReportCard`, `ReportCardRevision`, `ReportCardAuditEvent` | Reuse finalized state and audit workflow. |
| Report-card credits | `CreditPackage`, `CreditPayment`, `CreditAccount`, `CreditTransaction`, `ReportCardBilling` | Reuse for this product only; preserve ledger and one-credit-per-term invariants. |
| Offline CBT pricing/license | `ServicePlan`, `ServiceEntitlement` | Reuse plan and entitlement. Add a payment-order/fulfillment link so verified CBT purchase activates the correct entitlement without touching credit balances. |
| Webhook evidence | None | Add an append-only `PaymentWebhookEvent` or equivalent: provider event identity/hash, reference, signature-valid flag, received/processed timestamps, outcome, safe redacted payload, retry/error status. Never store secret keys. |
| CBT/report card payment separation | Distinct product type/fulfillment | Enforce product-type-specific fulfillment and idempotency keys in DB/service layer. |

## 6. Required/changed API surface for the next implementation phase

Existing endpoints under `/api/v1/billing/`: `GET billing/credits/`, `GET billing/packages/`, `POST billing/purchases/`, `GET billing/payments/`, `GET/POST billing/payments/{reference}/`, `GET billing/transactions/`, `GET billing/report-card-records/`, and public signed `POST billing/paystack/webhook/`.

Existing service routes: `GET services/plans/`, `GET services/entitlements/`, `GET services/entitlements/{id}/license/`, and platform-admin-only `GET/POST platform/services/entitlements/`.

For CBT checkout, add an authenticated, school-scoped purchase initialization endpoint and payment status/verification endpoint. The server must identify school from active membership, fetch active `offline_cbt` plan and derive amount/capacity/duration server-side, create a unique pending order reference, initialize Paystack, then fulfill only after verified success by creating/renewing the matching entitlement. The webhook should locate the order by unique reference and invoke the same idempotent fulfillment service. No frontend-supplied price or school ID should authorize or alter order ownership.

## 7. Security and operational checks

- Tenant queries for billing/entitlements must always derive school from active membership; test cross-school payment, status, entitlement, license and webhook-reference paths.
- Keep secret key and signing keys out of React bundles, browser storage, exception messages, logs and Git.
- Preserve immutable credit ledger; never directly edit balances or delete entries. Keep refund/reversal policy explicit and reconcile instead of automatically clawing back spent credits.
- Verify raw-body webhook HMAC with constant-time comparison (present); ensure event processing remains idempotent and add persistent audit evidence.
- Validate provider verification status/reference/amount/currency/ownership/product purpose before each product's fulfillment. Callback cannot grant product value.
- Production needs private PostgreSQL networking, backups and tested restores, TLS, secret rotation procedures, monitoring, rate limits where needed, private media storage, SMTP verification, and a controlled database migration path.
- Current production settings default HSTS to 31536000 seconds and enforce HTTPS when debug is off. Confirm TLS/proxy/domain configuration before enabling production traffic; do not set preload/include-subdomains prematurely.
- Ensure Vercel's built `VITE_API_BASE_URL` points to the actual Railway API; Vite values are build-time public values and must contain no secrets.

## 8. Test matrix before CBT payments or pilot deployment

**Existing billing tests** should be retained and run on PostgreSQL as well as SQLite. Extend with:

- Missing Paystack secret; invalid/unknown references; failed/abandoned status; amount, currency, reference, ownership and product-purpose mismatches.
- Webhook bad signature, malformed JSON, duplicate delivery, out-of-order events, provider retry, valid duplicate charge success, and persisted event evidence.
- Concurrent callback and webhook for one payment; exactly one credit allocation/entitlement activation.
- CBT plan purchase activates only `offline_cbt` entitlement, correct dates/capacity, and no report-card credit change; report-card package changes credits only and grants no CBT entitlement.
- Two-school isolation for purchase initialization, payment polling, transaction history, license download, and fulfillment.
- Report-card preview/download/reprint are free; first successful finalization costs exactly one credit; later revisions/duplicate calls do not charge again; insufficient balance blocks finalization atomically.
- Concurrent report-card finalizations cannot overspend one school's balance on PostgreSQL row locks.
- Railway smoke test for migrations, `/api/v1/health/database/`, Django admin static assets, SMTP verification, Vercel CORS/CSRF/JWT refresh, Paystack test checkout/webhook and private media persistence.
- Backup restore rehearsal using non-production data and a documented rollback/release procedure.

Relevant existing test files: `backend/apps/billing/tests.py`, `backend/apps/entitlements/tests.py`, `backend/apps/report_cards/tests.py`, `backend/apps/core/tests.py`, plus tenant and auth tests under `backend/apps/{schools,accounts}/tests.py`.

## 9. Recommended sequence

1. Confirm hosting domains, private media provider, SMTP sender, and Railway project/service ownership.
2. Prepare Railway runtime (Gunicorn, static serving, health-check path, one-shot migrations) and environment template; keep frontend on Vercel.
3. Exercise central app on Railway PostgreSQL with no real school data; validate migrations, admin/static, CORS/CSRF/JWT cookies, SMTP, media storage, backups, logs, and restore.
4. Run existing Paystack **test-mode** report-card credit flow end-to-end and add the test matrix gaps.
5. Implement the separately scoped CBT purchase order and idempotent entitlement fulfillment using `ServicePlan`/`ServiceEntitlement`; add webhook event persistence and tests.
6. Pilot test CBT purchase, license issuance/download, school-local import and offline expiration behavior. Keep live Paystack disabled until reconciliation, refund policy, and operator procedures are reviewed.
7. Only after test-mode sign-off, configure live Paystack credentials in Railway secrets and switch the provider account to live mode. Deploy explicitly; this audit did not create Railway resources or deploy anything.

## Audit disposition

**Railway:** not deployment-ready, but PostgreSQL and most Django production security settings are already supported. Runtime/static/media/release configuration and operational evidence are missing.
**Paystack report-card credits:** implemented with substantial safeguards; requires production test-mode rehearsal and the webhook evidence/verification policy decision.
**Paystack CBT purchases:** not implemented. Entitlements and plans exist, but payment-to-entitlement fulfillment is not connected.
**Implementation boundary:** this phase produces the requested inspection and plan only. No code, migration, account, database, Railway project, Paystack credential, or deployment was modified.
