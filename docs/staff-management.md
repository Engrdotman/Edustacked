# Staff management and teacher assignments (Module 6)

Module 6 adds school-scoped employment records and teaching responsibilities. Staff records do not create authentication accounts. A profile can link to an existing user only when that user already has an active membership in the same school. Linking never changes the membership role. If someone leaves a school, an administrator should end their staff record and separately review/deactivate that school's membership; their account and memberships in other schools are unaffected.

Employment states are active, inactive, suspended, and former. Former records are historical and cannot be reactivated. Teacher designations are stored separately from the staff profile. Assignment rows explicitly name a teacher, academic session, class, arm, subject, and start/end dates. A responsibility change ends the old row and creates a linked replacement; duplicate active assignments for the same teacher and academic placement are rejected. Multiple teachers and subjects remain allowed. There is no hardcoded teaching-load limit.

## API

Use the authenticated active school in `X-School-ID`; the server resolves it against the user's membership.

- `GET/POST /api/v1/staff/`: paginated directory, search by name/staff number/job title, and authorized profile creation.
- `GET/PATCH /api/v1/staff/{id}/`: retrieve/update staff details and employment status.
- `GET/POST/PATCH /api/v1/staff/{id}/teacher/`: inspect, designate, or update teacher-specific profile fields/status.
- `GET /api/v1/staff/me/`: teacher's own linked profile.
- `GET/POST /api/v1/assignments/`: list/search/filter assignments and create teaching responsibility. Filters: `academic_session`, `class_level`, `class_arm`, `subject`, `teacher`, and `status`.
- `GET /api/v1/assignments/{id}/`: school-scoped assignment detail; teachers can view only their own.
- `POST /api/v1/assignments/{id}/transition/`: end/cancel an active assignment, for example `{"status":"ended","end_date":"2027-01-31"}`.
- `POST /api/v1/assignments/{id}/replace/`: atomically end the old assignment and create its successor using the same required fields as assignment creation plus optional `reason`.

Example assignment request:

```json
{
  "teacher": 12,
  "academic_session": 3,
  "class_level": 4,
  "class_arm": 8,
  "subject": 15,
  "start_date": "2026-09-01"
}
```

School admins and managers can manage profiles, teacher designation, and assignments. Receptionists can view the basic staff directory. Teachers can view `/staff/me/` and only their own assignment list/detail. Accountants cannot access staff data in this module. Every write and related-object lookup is school-scoped and checked server-side.

## Manual verification

1. Apply migrations using `.venv\Scripts\python.exe backend\manage.py migrate`.
2. Sign in as an admin or manager and create staff records with distinct staff numbers. Verify case-insensitive duplicates fail in the same school while another school can reuse the number.
3. Link a staff record to an existing same-school member by account ID. Try a user with no active membership and confirm rejection; verify the user's school role does not change.
4. Designate a staff member as a teacher, add a teaching assignment using the existing session/class/arm/subject setup, and try a duplicate active responsibility.
5. End and replace an assignment. Confirm both rows remain in assignment history and the replacement points to the old row. Try ending/reactivating terminal assignments and assigning inactive/former staff.
6. Sign in as receptionist, teacher, and an admin from the other demo school. Confirm only the documented directory, own-profile, and own-assignment views are available and that foreign-school IDs return not found.
7. Set an assigned teacher to inactive/former and confirm active assignments are ended or cancelled while the user account and other school memberships remain unchanged.

## Checks and limits

Backend tests: `.venv\Scripts\python.exe backend\manage.py test apps.staff.tests --verbosity 1`. Full regression suite includes `apps.staff.tests` with Modules 1–5. Frontend build: run `npm.cmd run build` from `frontend`.

The module does not send invitations, create accounts, revoke unrelated memberships, implement payroll, or impose teaching-load limits. Invitations and configurable workload policy remain future work. Deployment checks in this workspace use SQLite; PostgreSQL should also be exercised in the deployment environment.
