# EDUstacked Railway Setup (Django API + PostgreSQL)

This guide matches the current repository layout. It configures the Django API on Railway and leaves the React frontend on Vercel. The Railway and Vercel accounts/domains are configured by the project owner; this document does not create or deploy external resources.

## Recommended service layout

- **Railway service `Postgres`:** one private Railway PostgreSQL service for the central SaaS database. All schools share this database and are separated by school membership and `school_id` scope. Do not create a database per school.
- **Railway service `backend`:** connect the GitHub repository, set **Root Directory** to `/backend`, and deploy the Django API from that directory.
- **Vercel:** continue to serve the React/Vite frontend in `/frontend`.
- **Offline CBT:** its LAN server is a separate school-side Django + SQLite application in `/local_cbt_server`; do not deploy that server as the central Railway API.

Railway's PostgreSQL service exposes a private `DATABASE_URL`. Reference it from the backend service instead of enabling public database networking. Railway documents PostgreSQL as private by default and provides `DATABASE_URL`; its pre-deploy command is intended for migrations and runs with service variables/network access. See [Railway PostgreSQL](https://docs.railway.com/databases/postgresql) and [Pre-Deploy Command](https://docs.railway.com/deployments/pre-deploy-command).

## Railway service settings

Set the backend service's source branch to the branch you intend Railway to deploy. The repository is currently on `develop`; use that only for a development/staging Railway environment. Use `main` for production after the reviewed production changes have been merged there.

| Setting | Value |
|---|---|
| Root Directory | `/backend` |
| Builder | Railpack / automatic Python detection |
| Build Command | `python -m pip install --upgrade pip && python -m pip install -r requirements.txt gunicorn` |
| Pre-Deploy Command | `python manage.py migrate --noinput` |
| Start Command | `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Healthcheck Path | `/api/v1/health/database/` |
| Restart policy | On failure (with a reasonable retry limit) |

The root directory matters: from `/backend`, the actual Django settings and entry point are `config.settings` and `config.wsgi:application`, `manage.py` is in the same directory, and `requirements.txt` is available there. Railway supports service build/start command overrides and pre-deploy commands; see [Build and Start Commands](https://docs.railway.com/builds/build-and-start-commands).

**Dependency note:** `gunicorn` is not currently in `backend/requirements.txt`. The build command above installs it for the Railway image. Before treating this as a stable production setup, pin Gunicorn in `backend/requirements.txt` so local, CI, and Railway installs match. The project also has no WhiteNoise setup. Django's `collectstatic` can collect admin assets, but they will not be served by this app until a static-file serving solution is configured. Add/configure WhiteNoise (or another deliberate static host) before relying on Django admin's CSS/JS.

Do not put migrations in the web start command. The pre-deploy command runs once for the deployment before the new web process starts; the main command should only start Gunicorn. Avoid the existing GitHub production workflow's database migration step targeting the same production database at the same time as Railway migrations. The workflow in this repository publishes a GitHub release package and is not the Railway deployer.

## Backend Railway variables

Create these in **backend service → Variables**. Do not paste actual secrets into Git, this Markdown file, the frontend, or chat. Railway accepts reference variables such as `${{Postgres.DATABASE_URL}}`; use the exact PostgreSQL service name shown in your Railway project. Railway variables apply to builds and running deployments; review and deploy staged variable changes. See [Railway Variables](https://docs.railway.com/variables).

| Variable | Value / purpose |
|---|---|
| `DJANGO_SECRET_KEY` | A newly generated, long, random production secret. Never reuse the checked-in example or a local/test key. |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (change `Postgres` if your Railway database service has another name). This project already parses PostgreSQL URLs and requires PostgreSQL when debug is off. |
| `DJANGO_ALLOWED_HOSTS` | Railway API hostname, e.g. `edustacked-api-production.up.railway.app`, plus any API custom domain. Hostnames only: no scheme, path, or wildcard. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Exact frontend origins, e.g. `https://your-vercel-project.vercel.app,https://www.yourdomain.ng`. Include every actual production frontend origin; no paths or trailing slash. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Full origins with scheme, e.g. `https://your-vercel-project.vercel.app,https://www.yourdomain.ng`. |
| `AUTH_REFRESH_COOKIE_SAMESITE` | Set to `None` for separate Vercel/Railway domains; the refresh cookie is Secure and HttpOnly. |
| `CSRF_COOKIE_SAMESITE` | Set to `None` so browser requests can send the CSRF cookie to the Railway API. Both cookies require HTTPS in production. |
| `FRONTEND_BASE_URL` | Exact HTTPS frontend origin, e.g. `https://www.yourdomain.ng`. The code reads this name when it creates Paystack callback URLs. |
| `EMAIL_BACKEND` | For SendGrid Web API use `apps.core.sendgrid_backend.SendgridBackend`; for SMTP use `django.core.mail.backends.smtp.EmailBackend`. |
| `SENDGRID_API_KEY` | Required server-only SendGrid key when using the SendGrid Web API backend. Keep it in Railway's secret variables; never put it in Vercel or source. |
| `SENDGRID_SANDBOX_MODE` | `false` for real delivery; `true` accepts test requests without delivering messages. |
| `EMAIL_HOST` | Required only for SMTP: hostname from the chosen email provider. |
| `EMAIL_PORT` | SMTP only; usually provider-specific `587` (STARTTLS) or `465` (implicit TLS). |
| `EMAIL_HOST_USER` | SMTP only: username. |
| `EMAIL_HOST_PASSWORD` | SMTP only: password/API credential; keep secret. |
| `EMAIL_USE_TLS` | SMTP only: `true` for STARTTLS where required; do not also set SSL true. |
| `EMAIL_USE_SSL` | SMTP only: `true` if the provider requires implicit TLS; do not also set TLS true. |
| `DEFAULT_FROM_EMAIL` | Verified sender, such as `EDUstacked <edustackedng@gmail.com>` if that address is configured to send through the SMTP provider. |
| `PAYSTACK_SECRET_KEY` | Start with a Paystack test secret (`sk_test_...`) for test-mode checkout. The key is server-only. Set a live secret only after test-mode acceptance and business approval. |
| `CBT_LICENSE_SIGNING_KEY` | Stable, long random secret for central CBT license signing; coordinate the matching verifier secret with each school-local server. |
| `CBT_PACKAGE_SIGNING_KEY` | A separate stable random secret for signed exam packages; coordinate with local CBT servers. |
| `CBT_OFFLINE_GRACE_DAYS` | Optional; defaults to `7`, allowed range `0`–`90`. |
| `DJANGO_LOG_LEVEL` | `INFO` |
| `DB_CONN_MAX_AGE` | `60` initially; tune to Railway PostgreSQL connection limits and application worker count. |
| `DB_CONNECT_TIMEOUT` | `5` initially. |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` only after HTTPS and custom domains have been verified. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `false` until every covered subdomain is guaranteed HTTPS. |
| `DJANGO_SECURE_HSTS_PRELOAD` | `false` unless the domain has been deliberately submitted for preload. |
| `AUTH_LOGIN_RATE` | Optional; defaults to `10/minute`. |
| `AUTH_LOGIN_FAILURE_LIMIT` | Optional; defaults to `5`. |
| `AUTH_LOGIN_FAILURE_WINDOW_SECONDS` | Optional; defaults to `900`. |
| `AUTH_LOGIN_LOCKOUT_SECONDS` | Optional; defaults to `900`. |

The code does **not** read `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL`, `PAYSTACK_MODE`, or `PAYSTACK_PUBLIC_KEY`. Use the project-specific names above. In the current provider, test/live selection is controlled by which Paystack secret key is configured; do not add a frontend secret key. `VITE_API_BASE_URL` belongs in Vercel, not Railway.

### Generate secrets locally

Run this in a trusted local terminal for each independent secret, then paste the output directly into the appropriate Railway secret field. Do not commit the output:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Generate distinct values for `DJANGO_SECRET_KEY`, `CBT_LICENSE_SIGNING_KEY`, and `CBT_PACKAGE_SIGNING_KEY`. The CBT signing values must remain stable across deployments and must match the configured school-local verifier where the current symmetric signing architecture requires it.

## Vercel frontend variable

In the Vercel project for `/frontend`, set this for Production (and set appropriate API URLs separately for Preview/Development):

```dotenv
VITE_API_BASE_URL=https://<your-railway-api-domain>/api
```

Vite embeds `VITE_` values into the public browser build. Never put a Paystack secret, Django secret, SMTP password, database URL, or CBT signing key in a `VITE_` variable. After changing this variable, trigger a Vercel rebuild so the new API origin is compiled into the frontend.

## PostgreSQL tables: use Django migrations

**Do not manually create the application tables with hand-written `CREATE TABLE` SQL.** This repository has Django models and migrations across accounts, schools, academics, students, staff, attendance, results, report cards, billing, entitlements, CBT, parent portal, and reporting. The migrations create the schema, indexes, constraints, and data migrations together and update Django's `django_migrations` history. Raw SQL would leave that history inconsistent and can omit required constraints or migration data transformations.

Set the backend's private `DATABASE_URL` reference, then run the following as the Railway backend service's **Pre-Deploy Command** from its `/backend` root:

```bash
python manage.py migrate --noinput
```

For a one-time manual first deployment, the same command can be run from the Railway backend service shell/CLI after the backend has the PostgreSQL reference variable. Do not run it against a laptop database and assume it creates Railway tables. The application's new database will have its schema created by all unapplied migrations; it does not require a manually written SQL script.

Useful schema checks (run in the backend service shell):

```bash
python manage.py showmigrations
python manage.py migrate --plan
```

Optional read-only check in Railway's PostgreSQL query console after migrations:

```sql
SELECT app, name, applied
FROM django_migrations
ORDER BY applied, app, name;
```

To inspect generated SQL for an individual migration locally, use `python manage.py sqlmigrate <app_label> <migration_name>` with the correct settings and a reachable PostgreSQL database. That SQL is for review/debugging, not a replacement for running `migrate`.

## First deployment checklist

1. Add Railway PostgreSQL; keep it private.
2. Set backend Root Directory `/backend`, build/start commands, pre-deploy migration, and database health-check path.
3. Add required backend variables and exact Vercel origin values. Keep secrets in Railway's variable vault.
4. Configure Vercel `VITE_API_BASE_URL` and rebuild the frontend.
5. Deploy the backend, inspect build/runtime logs, and confirm Railway health check succeeds at `/api/v1/health/database/`.
6. Confirm Django admin static assets. If unstyled, finish WhiteNoise/static-host configuration before relying on admin.
7. Test signup/verification email, login/refresh/logout across the production Vercel/Railway domains, and a Paystack **test-mode** purchase. Do not switch to live Paystack until that flow and webhook are verified.
8. Configure durable private media storage before uploading real school logos, signatures, student/staff photos, or CBT assets. `MEDIA_ROOT` currently points to local app disk and is not a durable object-storage integration.
9. Take a database backup and rehearse restore before importing real school data.

## Current project limitations to resolve before production use

~~- `gunicorn` is not pinned in `backend/requirements.txt` (the sample build command installs it for Railway).~~ ✅ **FIXED:** Pinned to `gunicorn>=23.0,<24`

~~- WhiteNoise/static serving is not configured; `collectstatic` alone does not serve Django admin files.~~ ✅ **FIXED:** WhiteNoise middleware and storage configured in settings.py

- Media uses local `MEDIA_ROOT`; persistent private object storage is not connected. **ACTION REQUIRED:** See `docs/media-storage-setup.md` for S3/Railway Volumes/Supabase options before uploading production files.

~~- SMTP values must be supplied to send verification and password-reset emails.~~ ✅ **FIXED:** EMAIL_HOST_USER validation added; production deployment fails if not configured.

- The current report-card credit Paystack flow exists, but Paystack does not yet purchase/activate Offline CBT entitlements. **Do not sell CBT packages until that separate payment fulfillment is implemented and tested.** See `docs/cbt-payment-fulfillment.md` for implementation roadmap.

~~- The current GitHub production workflow publishes a release package and is not configured as Railway deployment. Ensure only one deployment path runs production migrations.~~ ✅ **FIXED:** GitHub workflow removed migrations; Railway Pre-Deploy Command is now the single source of truth. See `docs/railway-deployment-checklist.md`.

## What Changed in This Update

1. **requirements.txt:** Added `gunicorn>=23.0,<24` and `whitenoise>=6.8,<7`
2. **settings.py:** 
   - Added WhiteNoise middleware (before CORS)
   - Configured `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"`
   - Added email validation: production requires `EMAIL_HOST_USER`
3. **GitHub workflow (deploy-production.yml):**
   - Removed database migrations (they were running twice: in GitHub and Railway)
   - Kept static file collection for WhiteNoise
   - Updated release notes to clarify package-validation-only purpose
   - Documented "deploy to Railway" instructions in release body
4. **New documentation:**
   - `docs/railway-deployment-checklist.md` — Complete step-by-step Railway setup and troubleshooting
   - `docs/media-storage-setup.md` — Options for persistent object storage before production
   - `docs/cbt-payment-fulfillment.md` — Roadmap for CBT entitlement fulfillment via Paystack

## Updated Build Command for Railway

The Railway backend service **build command** can now be simplified (no longer needs to install gunicorn separately):

```bash
python -m pip install --upgrade pip && python -m pip install -r requirements.txt
```

The Start Command remains:
```bash
python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```
