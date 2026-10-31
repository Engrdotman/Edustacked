# Parent and Guardian Portal (Module 11)

The portal is a read-only, authenticated view over existing guardian, student, enrollment, attendance, and report-card records. It does not create a second student directory or grant a school membership to a guardian.

## Account and linking flow

1. Staff create/reuse a school guardian and an active `StudentGuardian` link through the student-management workflow.
2. A staff member with `students.guardians.manage` issues an invitation for that exact active link. The guardian's email must be present on the school record.
3. The backend emails a random, single-use activation URL. Only its SHA-256 hash is stored. The default expiry follows Django's `PASSWORD_RESET_TIMEOUT` (one day unless deployment configuration changes it). Resending revokes earlier outstanding invitations.
4. A new guardian chooses a password; an existing EDUstacked account must verify its password before the guardian profile is attached. Activation creates no staff membership or role.
5. Access is computed from active `Guardian.user` associations and active guardian-student links. Revoking the link or deactivating the guardian immediately removes portal access while preserving student/enrollment history.

Email delivery uses Django's configured email backend and `DEFAULT_FROM_EMAIL`. Development uses the local in-memory backend; deployments need valid SMTP/provider settings and a correct `FRONTEND_BASE_URL` with HTTPS. No real invitation mail was sent during development verification.

## Permissions and privacy

Guardians can read their own limited profile, linked student overview, finalized attendance, finalized report-card snapshots/PDFs, published announcements for linked schools, and their own notifications. IDs are authorized through the authenticated account on each request; inaccessible student/report-card resources return not found. Parent portal routes do not accept a guardian ID as authority.

Staff retain control of guardian links, invitations, and announcements. Only school administrators/managers with `announcements.manage` can manage school announcements; only staff with `students.guardians.manage` can invite guardians. Guardians have no staff membership and cannot access staff student, attendance, assessment, report-card, or billing operations. Published report-card viewing/PDF rendering uses Module 9 finalized snapshots and does not consume Module 10 credits.

Attendance aggregates reuse Module 7's finalized-register service. Draft registers and records without a status are omitted. Missing registers are not counted as absences; present and late count as attended, while absent and excused are included in the denominator. Staff-only attendance notes are not returned.

Security-relevant events include invitation sent/accepted, profile update, link/guardian revocation, and unauthorized student/report access attempts. Invitation secrets, passwords, internal attendance notes, and unrelated guardian details are not returned to the portal.

## API

All paths are under `/api/v1/` and use the existing JWT authentication except activation.

| Method | Path | Access |
| --- | --- | --- |
| POST | `guardian/activate/` | Public, rate limited; one-time invitation token |
| GET, PATCH | `parent/profile/` | Authenticated linked guardian; limited name fields editable |
| GET | `parent/students/` | Authenticated guardian; active linked students only |
| GET | `parent/students/{student_id}/` | That guardian's linked student |
| GET | `parent/students/{student_id}/attendance/` | Linked student; supports `session`, `start_date`, `end_date`, and pagination |
| GET | `parent/students/{student_id}/report-cards/` | Finalized revisions for linked student |
| GET | `parent/report-cards/{revision_id}/` | Authorized finalized snapshot |
| GET | `parent/report-cards/{revision_id}/pdf/` | Authorized finalized PDF; access checked per request |
| GET | `parent/announcements/` | Published/unexpired announcements from linked schools |
| GET | `parent/notifications/` | Current guardian's notifications |
| POST | `parent/notifications/{id}/read/` | Current guardian's notification only |
| POST | `parent/staff/students/{student_id}/guardians/{link_id}/invite/` | Staff permission `students.guardians.manage` |
| GET, POST | `parent/staff/announcements/` | Staff permission `announcements.manage` |
| PATCH | `parent/staff/announcements/{id}/` | Owning school, `announcements.manage` |
| POST | `parent/staff/announcements/{id}/publish/` | Owning school, `announcements.manage` |
| POST | `parent/staff/announcements/{id}/archive/` | Owning school, `announcements.manage` |

## Schema additions

- `students_guardian.user_id`: nullable link to the existing account user. A user may have multiple guardian records (for siblings or schools); guardian access still requires each active relationship.
- `parent_portal_guardianinvitation`: guardian, inviting/accepting accounts, email snapshot, token hash, expiry, acceptance/revocation timestamps.
- `parent_portal_announcement`: school, title/message, draft/published/archived state, publication/expiry dates, staff authorship.
- `parent_portal_portalnotification`: recipient, optional student/announcement, event key, content, created/read timestamps; unique `(user, event_key)` makes trusted event retries idempotent.
- `parent_portal_portalauditevent`: append-only security events with actor, optional guardian/link, action, minimal metadata, timestamp.

Migrations are additive: `students/0002_guardian_user` and `parent_portal/0001_initial`. Apply with `python backend/manage.py migrate` (or `python manage.py migrate` from `backend/`). Do not reset the database.

## Frontend

Parents sign in through the existing login page. New accounts use `/guardian/activate?token=...`; activation removes the token from browser history before submitting it. Parent accounts land on `/parent`, which provides student selection, school/class/session overview, attendance, finalized report cards/PDFs, announcements, notifications, limited profile editing, and logout. Staff with the applicable permission see an announcement management link. The backend remains the access boundary.

## Verification

```powershell
.venv\Scripts\python.exe backend\manage.py check
.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe backend\manage.py test apps.parent_portal.tests --verbosity 1
.venv\Scripts\python.exe backend\manage.py test apps.core.tests apps.accounts.tests apps.schools.tests apps.academics.tests apps.students.tests apps.staff.tests apps.attendance.tests apps.results.tests apps.report_cards.tests apps.billing.tests apps.parent_portal.tests --verbosity 1
npm.cmd run build # from frontend/
```

