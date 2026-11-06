# Development setup

## Requirements

- Python 3.10 or newer (Django 5.2 LTS supports Python 3.10+).
- Node.js 20.19+ or 22.12+ (supported by the selected Vite release).
- npm, included with Node.js.
- SQLite for local development (included with Python).
- PostgreSQL 14 or newer for deployment.

## Backend (Windows PowerShell)

From the repository root:

1. Create and activate a virtual environment: `py -m venv .venv`, then `\.venv\Scripts\Activate.ps1`.
2. Install dependencies with the activated interpreter: `python -m pip install -r backend/requirements.txt`.
3. Create the local environment file: `Copy-Item backend/.env.example backend/.env`; set `DJANGO_SECRET_KEY` to a random local value. SQLite is selected by default and needs no database login.
4. Apply migrations: `python backend/manage.py migrate`. This creates `backend/db.sqlite3`.
5. Check configuration and run tests: `python backend/manage.py check` and `python backend/manage.py test apps.core.tests apps.accounts.tests apps.schools.tests`.
6. Start the API: `python backend/manage.py runserver`.

For deployment, set `DJANGO_DEBUG=false` and `DB_ENGINE=postgresql`; provide `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` from the secret manager. Connection pooling and timeout settings are `DB_CONN_MAX_AGE` and `DB_CONNECT_TIMEOUT`. Other settings include `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_LOG_LEVEL`, `DJANGO_SECURE_HSTS_*`, JWT lifetimes, refresh-cookie settings, and SMTP `EMAIL_*` settings. Enable HSTS subdomains or preload only after every covered host is permanently HTTPS-ready. Never commit local or production credentials.

## Frontend (separate terminal)

1. Copy `frontend/.env.example` to `frontend/.env`. For local development, leave `VITE_API_BASE_URL` empty; Vite proxies `/api` to `http://127.0.0.1:8000` so browser requests remain same-origin.
2. Install dependencies: `cd frontend`, then `npm.cmd install`.
3. Start Vite: `npm.cmd run dev`.
4. Verify a production bundle with `npm.cmd run build`.

The Vite development server normally listens at `http://localhost:5173`. The frontend proxy forwards `/api/*` to the Django server, normally `http://127.0.0.1:8000`, and can be changed with `VITE_DEV_API_PROXY`. For Vercel production, set `VITE_API_BASE_URL` in the Vercel project to `https://<your-railway-api-domain>/api`, then rebuild. On Railway, allow the exact Vercel site origin in `DJANGO_CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS`; production refresh and CSRF cookies default to `SameSite=None; Secure` for this cross-site setup. Health endpoints are `/health/` and `/health/database/`. Local email defaults to Django's in-memory backend; configure SMTP or a local mail-capture service to manually receive password reset and account setup links.

## Project commands

After activating `.venv`, run backend commands from the repository root using `python backend/manage.py <command>`. Run frontend commands from `frontend/` using `npm.cmd`. Create new schema migrations with `python backend/manage.py makemigrations`, inspect them, then apply them with `python backend/manage.py migrate`. Run `python backend/manage.py flushexpiredtokens` daily in deployment to clean expired refresh-token records. Do not edit an applied migration or run destructive database commands as a routine setup step.
