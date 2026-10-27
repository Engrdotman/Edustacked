# EDUstacked

A modular-monolith School Management System for Nigerian schools. Modules 1 and 2 provide the Django/React foundation, school tenant identity, email-based authentication, secure sessions, school memberships, and role-based API permissions. School business workflows and billing remain later modules.

## Repository layout

- `backend/` — Django and Django REST Framework API.
- `frontend/` — React application built with Vite.
- `docs/` — architecture, local setup, and module roadmap.
- `docs/authentication-and-rbac.md` — authentication API, role matrix, and first-admin setup.

## Prerequisites

- Python 3.10 or newer and pip.
- Node.js 20.19+ or 22.12+ and npm.
- SQLite for local development.
- PostgreSQL 14 or newer for deployment.

## Windows setup

See [docs/development-setup.md](docs/development-setup.md) for the full PowerShell setup. In summary:

1. Create and activate a virtual environment, then install `backend/requirements.txt` with that environment's Python:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend/requirements.txt
   ```

2. Copy `backend/.env.example` to `backend/.env` and set `DJANGO_SECRET_KEY` to a random local value. SQLite is ready without database credentials.
3. Run `python backend/manage.py migrate`. This creates `backend/db.sqlite3` for local development.

4. Start Django with `python backend/manage.py runserver`.
5. In another terminal, copy `frontend/.env.example` to `frontend/.env`, run `npm.cmd install`, then `npm.cmd run dev`.

Run the backend checks and automated tests with:

```powershell
python backend/manage.py check
python backend/manage.py test apps.core.tests apps.accounts.tests apps.schools.tests
```

## Database and configuration

Development defaults to SQLite. Deployment should set `DJANGO_DEBUG=false` and `DB_ENGINE=postgresql`, then provide `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` from the deployment secret manager. Connection pooling and timeouts use `DB_CONN_MAX_AGE` and `DB_CONNECT_TIMEOUT`. Django settings include `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_LOG_LEVEL`, `DJANGO_SECURE_HSTS_*`, JWT lifetimes, refresh-cookie settings, and configurable `EMAIL_*` settings. SQLite is rejected when `DJANGO_DEBUG=false`. The frontend API URL is configured with `VITE_API_BASE_URL`.

For a PostgreSQL deployment, create an application role and database (replace the example password; do not commit it):

```sql
CREATE ROLE school_management LOGIN PASSWORD 'use-a-secret-manager-value';
CREATE DATABASE school_management OWNER school_management;
```

## Scope and security

The tenant strategy uses a shared database with application-enforced school scoping: SQLite locally and PostgreSQL in deployment. The reusable `SchoolScopedQuerySetMixin` resolves a school through the authenticated user's active membership and scopes list/object querysets. The versioned API starts at `/api/v1/`; health endpoints are `/api/v1/health/` and `/api/v1/health/database/`. Authentication and RBAC endpoints are described in [authentication-and-rbac.md](docs/authentication-and-rbac.md). See the [database schema](docs/database-schema.md) and [architecture](docs/architecture.md) before adding tenant-owned data.

Public self-registration is disabled. Initial superadmin setup and account provisioning are restricted; students, attendance, fees, results, report cards, credits, and payment workflows remain out of scope.
