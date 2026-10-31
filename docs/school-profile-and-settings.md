# School profile and settings (Module 3)

Module 3 adds an editable school profile, basic per-school preferences, and protected logo upload/display. It does not add academic sessions, terms, classes, subjects, students, attendance, fees, grading rules, or billing.

## Data model

- `School` is extended in place with logo, state, local government area, website, motto, and description. Its primary key, unique slug/code, active status, existing contacts, and timestamps remain intact. The profile API treats the slug and status as read-only.
- `SchoolSettings` has a one-to-one relationship with `School`. New schools receive settings with NGN, Africa/Lagos, DD/MM/YYYY, an “Academic year” label, email/phone contact preferences, and the existing EDUstacked green brand color. Migration `schools/0007_*` gives existing schools the same defaults.
- Logo files are generated under a per-school directory with random filenames. The API accepts JPG, PNG, or WebP images up to 2 MB; file binaries stay in media storage, not in the database.

## Permissions and tenant selection

Send the currently selected authorized school in the existing `X-School-ID` header. The identifier is resolved against an active membership (or an active school for a platform superadmin) on every request; it does not grant access by itself.

- School admin and platform superadmin: view and edit profile/settings, upload and retrieve logo.
- School manager, teacher, accountant, receptionist: read-only profile/settings and logo access.
- Legacy `member`: no access.
- Unauthenticated requests are rejected. Missing or unauthorized schools are denied without returning another school's data.

Profile editing does not allow a school admin to change the slug/code or active status. Platform privilege is still controlled only by Django `is_superuser`.

## API endpoints

All endpoints use `/api/v1/`, bearer access authentication, and the selected-school header.

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /schools/profile/` | `school.view` | Retrieve selected school information and `logo_present`. |
| `PATCH /schools/profile/` | `school.manage` | Update editable school profile fields. |
| `GET /schools/settings/` | `school.view` | Retrieve settings; initializes defaults safely if absent. |
| `PATCH /schools/settings/` | `school.manage` | Update currency, timezone, date display, label, contact preferences, and brand color. |
| `GET /schools/profile/logo/` | `school.view` | Stream the selected school's logo with private/no-store cache headers. |
| `POST /schools/profile/logo/` | `school.manage` | Multipart form upload with field `logo`. |

Profile update example:

```http
PATCH /api/v1/schools/profile/
Authorization: Bearer <access-token>
X-School-ID: 42
Content-Type: application/json

{"name":"Unity Academy","contact_email":"office@unity.example","state":"Lagos","local_government_area":"Ikeja","motto":"Learn and lead"}
```

Settings update example:

```json
{
  "default_currency": "NGN",
  "time_zone": "Africa/Lagos",
  "date_format": "DD/MM/YYYY",
  "academic_year_label": "School year",
  "contact_preferences": {"email": true, "phone": false},
  "branding_primary_color": "#285744"
}
```

Logo upload uses `multipart/form-data`, for example:

```bash
curl -X POST http://localhost:8000/api/v1/schools/profile/logo/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-School-ID: 42" \
  -F "logo=@school-logo.png"
```

Serializer errors return field-keyed HTTP 400 responses. The school code is displayed for reference but is not editable through profile updates.

## Media storage and deployment

Development stores files below `MEDIA_ROOT` (`backend/media` by default). The frontend never receives a raw media path: it requests the logo from the authenticated endpoint, which verifies the active school and streams the file. Upload names are replaced with generated identifiers.

Production must provide durable private storage (for example, a private object-storage bucket accessed by the Django storage backend) and backups. Do not expose `MEDIA_ROOT` as a public static directory or serve these files directly from a public bucket; that would bypass the logo endpoint's tenant authorization. No new environment variables are required for the local filesystem configuration. Configure storage credentials and bucket settings through deployment secrets when production object storage is selected.

## Migrations and verification

Run migrations from the project root:

```powershell
.venv\Scripts\python.exe backend\manage.py migrate
```

The migration adds nullable/optional profile data, creates `schools_schoolsettings`, and initializes defaults for existing schools without changing school IDs, slugs, or memberships.

Run all backend tests with:

```powershell
.venv\Scripts\python.exe backend\manage.py test apps.core.tests apps.accounts.tests apps.schools.tests --verbosity 1
```

Manual check: sign in as a school admin, choose an authorized school in the workspace, open **School profile & settings**, edit and save profile/settings, and upload an image. Sign in as a teacher or receptionist to verify read-only rendering. Use a user from a different school and attempt the same API requests with the first school's `X-School-ID`; requests must be denied. Switch between two authorized memberships and confirm profile/settings are independent.

## Frontend

The workspace links to `/app/school`. It loads profile/settings from the API and displays the selected school's logo using an authenticated blob request, with an initials placeholder when no logo exists. Only school admins and platform superadmins see editable controls; all authorization is enforced again by the API. Unsaved changes prompt before leaving, and save/cancel feedback appears beside the forms.
