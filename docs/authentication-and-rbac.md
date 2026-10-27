# Authentication, memberships, and RBAC

Module 2 adds authentication and authorization only. It does not add student, attendance, fee, result, or other school workflow APIs.

## Authentication approach

- Login identity is a normalized, unique email in `accounts_user.login_email`. Django's existing username and email fields are retained for compatibility. Passwords use Django's password hashers and validators.
- Public registration is disabled. Accounts are provisioned by a platform superadmin or an authorized school admin through the membership API. New provisioned accounts receive an unusable password and a password setup link.
- Simple JWT issues five-minute access tokens and seven-day refresh tokens by default. Access tokens are held in frontend memory and sent as a bearer token. They are not written to local storage or cookies.
- Refresh tokens are rotated and kept in an HttpOnly cookie scoped to `/api/v1/auth/`. The cookie is `Secure` in production, `SameSite=Lax` by default, and its domain/SameSite mode can be configured for the deployment topology. Logout and refresh rotation blacklist old tokens.
- Login, refresh, and logout require CSRF protection. The client first calls the CSRF bootstrap endpoint, then sends the returned token in `X-CSRFToken` and includes credentials. CORS credentials are enabled only for the configured origins.
- Password reset uses Django's one-time password-reset token generator. Links expire after `PASSWORD_RESET_TIMEOUT` (one hour by default). The request endpoint returns the same message whether or not the email belongs to an active account.
- Changing or resetting a password revokes outstanding refresh tokens and invalidates access tokens bound to the old password hash. Logout cannot revoke an already-issued access token; its short lifetime limits that window. School membership and role checks still run against the database for every protected school request.
- In development, the default email backend is in-memory so reset tokens are not written to console logs. Configure SMTP or a local mail-capture service to receive messages manually. Production defaults to SMTP configured through environment variables.

Simple JWT's refresh rotation and blacklist settings are enabled, and the blacklist app's migrations must be applied. See the [Simple JWT settings](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/settings.html) and [blacklist app docs](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html).

## Role and permission matrix

Platform superadmins are Django users with `is_superuser=True`; this flag is not assignable through the application API and is distinct from school membership roles. `is_staff` alone does not grant API platform authority.

| Role | Permissions currently defined |
|---|---|
| Platform superadmin | Platform-wide API access and school creation; can assign any school role. |
| School admin | School and membership administration; academic configuration; student, attendance, and result operations; finance; front desk. May provision non-admin school roles, but cannot assign another school admin or edit/revoke their own membership. |
| School manager | Academic configuration; student management; attendance management; view and enter results; front desk. No finance, membership administration, or result approval. |
| Teacher | View students; view/record attendance; view and enter results. |
| Accountant | Finance view and management only. |
| Receptionist / front desk | View/enroll students and manage front-desk operations. |
| Legacy `member` | No permissions. Kept only for compatibility with existing Module 1 memberships. |

These permission keys are groundwork for future business endpoints. This module exposes only school creation and membership administration; it does not create the underlying school workflows. The permission map is centralized in `apps.schools.permissions.ROLE_PERMISSIONS`.

Every non-platform school request must resolve an active school and active membership. `SchoolScopedQuerySetMixin` scopes querysets and object lookups; `HasSchoolPermission` checks the role and object school. A path ID or `X-School-ID` header is context, never proof of access. School admins can only administer schools where they hold an active admin membership. Inactive membership revocation takes effect on the next request.

## API endpoints

All endpoints use the `/api/v1/` prefix.

| Method and path | Access | Purpose |
|---|---|---|
| `GET /auth/csrf/` | Public | Bootstrap a CSRF token for browser requests. |
| `POST /auth/login/` | Public + CSRF | Sign in with email/password; returns access token and sets refresh cookie. |
| `POST /auth/refresh/` | Refresh cookie + CSRF | Rotate refresh token and return a new access token. |
| `POST /auth/logout/` | Refresh cookie + CSRF | Blacklist refresh token and clear the cookie. |
| `GET /auth/me/` | Authenticated | Current profile. |
| `GET /auth/schools/` | Authenticated | Active school memberships; platform superadmins see active schools. |
| `POST /auth/schools/select/` | Authenticated | Validate/select one of the user's authorized schools. |
| `POST /auth/password/change/` | Authenticated | Change password after verifying current password. |
| `POST /auth/password/reset/` | Public | Request a reset link; response is enumeration-safe. |
| `POST /auth/password/reset/confirm/` | Public + one-time token | Set a new password. |
| `POST /schools/` | Platform superadmin | Create a school. |
| `GET, POST /schools/{school_id}/memberships/` | School admin or platform superadmin | List memberships or provision an account for that school. |
| `GET, PATCH /schools/{school_id}/memberships/{membership_id}/` | School admin or platform superadmin | Read, change an allowed role, or deactivate a membership. |

School membership creation accepts `email`, optional `first_name`/`last_name`, and `role`. It does not accept `school`, `is_staff`, `is_superuser`, or a password. The authorized school comes from the URL and is checked against membership. Only a platform superadmin can assign `school_admin`.

### Browser login example

```js
const base = 'http://localhost:8000/api/v1'

const csrfResponse = await fetch(`${base}/auth/csrf/`, { credentials: 'include' })
const { csrfToken } = await csrfResponse.json()

const loginResponse = await fetch(`${base}/auth/login/`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
  body: JSON.stringify({ email: 'admin@example.com', password: 'your-password' }),
})
const { access, user } = await loginResponse.json()

const profileResponse = await fetch(`${base}/auth/me/`, {
  headers: { Authorization: `Bearer ${access}` },
  credentials: 'include',
})
```

The refresh token is set as an HttpOnly cookie and is not returned in JSON. The frontend keeps `access` in memory, refreshes it through `/auth/refresh/`, and clears it on logout.

### School selection example

```http
POST /api/v1/auth/schools/select/
Authorization: Bearer <access-token>
Content-Type: application/json

{"school_id": 12}
```

The client may send the returned school ID as `X-School-ID` to later tenant endpoints. Each endpoint must still resolve that ID against the user's active membership.

### Provisioning example

```http
POST /api/v1/schools/12/memberships/
Authorization: Bearer <platform-or-school-admin-access-token>
Content-Type: application/json

{"email":"teacher@example.com","first_name":"Ada","role":"teacher"}
```

The platform superadmin can assign `school_admin`. A school admin can provision manager, teacher, accountant, or receptionist roles for their own school. The new account receives a password setup link through the configured email backend.

## First platform superadmin and manual setup

1. Activate `.venv`, apply migrations, then create the first platform account from the repository root with `python backend/manage.py createsuperuser`. The command prompts for username, email, and password; use a unique monitored email address and a strong password.
2. Sign in at the frontend or obtain an access token through the login endpoint.
3. Create the first school through `POST /api/v1/schools/` or Django admin. Only `is_superuser=True` can create a school through the API.
4. Provision the first school admin with `POST /api/v1/schools/{id}/memberships/`, using `role: "school_admin"`. Configure a reachable SMTP or local mail-capture backend first so the setup link is received.
5. The school admin can then provision permitted non-admin staff roles. Use the frontend to sign in, select a school, and sign out; use the API to verify school creation and membership permissions.
6. Verify isolation by trying a different school ID or `X-School-ID`; a school admin must be denied outside their active membership. Deactivate the membership and confirm access is denied on the next request.

For manual password-reset testing, configure `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and the appropriate TLS setting. Do not use a console email backend in an environment where reset tokens must not appear in logs.

## Tests and maintenance

Run the backend suite with:

```powershell
python backend/manage.py test apps.core.tests apps.accounts.tests apps.schools.tests
```

Run `python backend/manage.py flushexpiredtokens` daily in deployment. Use a shared Django cache and suitable rate limits when deploying multiple API workers.
