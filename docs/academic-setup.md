# Academic setup and grading configuration (Module 4)

Module 4 adds school-specific academic sessions, terms, class levels, class arms, subjects, class-subject assignments, and grading scales/bands. These are configuration records only. Student enrollment, attendance, assessments, results, report cards, billing, and payments remain out of scope.

## Permissions and tenant context

All routes require an authenticated user and `X-School-ID`. The header is resolved through the authenticated user's active school membership on each request; it cannot grant access by itself. The existing `academics.manage` permission is granted to school admins and school managers, so those roles can manage academic setup. Teachers, accountants, receptionists, and legacy members cannot access these configuration endpoints. Platform superadmins retain their existing platform-wide bypass for active schools.

School ownership is always assigned by the backend. Term/session, arm/class, class/subject assignment, and grade-band/scale relationships are constrained to the selected school. Collection endpoints return page-number pagination (50 items by default, maximum 200). The React page follows pagination to load all rows for its local search.

## Models and behavior

- **Academic session:** school, unique session name, start/end dates, and `draft`, `active`, or `completed` status. New sessions start as drafts. A school can have one active session. Active sessions can only be completed; their details are locked. A session can be completed only after its terms are completed, and completed session data is immutable.
- **Term:** school, parent session, name, sequence, dates, and lifecycle status. Names and sequence numbers are unique within a session. Dates must fit in the parent session and may not overlap another term. Only terms in an active session can be activated; one term per session can be active. Completed terms are immutable.
- **Class level:** school-defined name, optional code, category, description, and active status. Names and nonblank codes are unique case-insensitively within the school.
- **Class arm:** parent class, name, description, and active status. Arm names are unique within the class.
- **Subject:** school-defined name, optional code and description, and active status. Names and nonblank codes are unique case-insensitively within the school.
- **Class-subject assignment:** connects one subject to one class, with duplicate pairs prevented and active status retained for safe deactivation.
- **Grading scale:** school-specific name, configurable maximum score (100.00 by default), description, and active status. No default Nigerian bands are created; each school configures its own policy.
- **Grade band:** label, inclusive minimum/maximum scores, description, optional grade point, and active status. Scores use two decimal places. Active bands cannot overlap. Activating a scale requires bands to cover 0.00 through the configured maximum with no gaps at 0.01 score increments. Deactivate a scale before changing its bands.

Classes, arms, subjects, assignments, grading scales, and bands are deactivated instead of deleted. Draft sessions and draft terms can be deleted only when the session has no terms / when the term has not been activated; historical or protected records cannot be removed. Foreign keys use `PROTECT` where future academic records will need to preserve configuration.

## API endpoints

All paths are prefixed by `/api/v1/academics/`.

| Method and path | Purpose |
|---|---|
| `GET, POST /academic-sessions/` | List/create sessions. |
| `GET, PATCH, DELETE /academic-sessions/{id}/` | Read/edit lifecycle or delete an empty draft session. |
| `GET, POST /terms/` | List/create terms; optionally filter with `?academic_session={id}`. |
| `GET, PATCH, DELETE /terms/{id}/` | Read/edit lifecycle or delete a draft term. |
| `GET, POST /classes/` | List/create class levels. |
| `GET, PATCH, DELETE /classes/{id}/` | Read/edit/deactivate a class level. |
| `GET, POST /classes/{class_id}/arms/` | List/create arms in the selected class. |
| `GET, PATCH, DELETE /classes/{class_id}/arms/{id}/` | Read/edit/deactivate an arm. |
| `GET, POST /subjects/` | List/create school subjects. |
| `GET, PATCH, DELETE /subjects/{id}/` | Read/edit/deactivate a subject. |
| `GET, POST /classes/{class_id}/subjects/` | List/create subject assignments for a class. |
| `GET, PATCH, DELETE /classes/{class_id}/subjects/{id}/` | Read/edit/deactivate an assignment. |
| `GET, POST /grading-scales/` | List/create grading scales. |
| `GET, PATCH, DELETE /grading-scales/{id}/` | Read/edit/deactivate a grading scale. |
| `GET, POST /grading-scales/{scale_id}/bands/` | List/create bands in a grading scale. |
| `GET, PATCH, DELETE /grading-scales/{scale_id}/bands/{id}/` | Read/edit/deactivate a grade band. |

The `school` property is read-only in responses and requests. Parent IDs are checked against the selected school. For example:

```http
POST /api/v1/academics/academic-sessions/
Authorization: Bearer <access-token>
X-School-ID: 42
Content-Type: application/json

{"name":"2026/2027","start_date":"2026-09-01","end_date":"2027-06-30"}
```

Create a term by supplying the parent session ID, a unique sequence, and dates within that session:

```json
{
  "academic_session": 11,
  "name": "First Term",
  "sequence": 1,
  "start_date": "2026-09-01",
  "end_date": "2026-12-18"
}
```

Validation errors use field-keyed HTTP 400 responses. Unauthenticated requests receive 401, authenticated roles without `academics.manage` receive 403, and an object or parent in another school is returned as not found.

## Frontend

From the selected school workspace, choose **Academic setup**. The `/app/academics` section has tabs for sessions and terms, classes and arms/assignments, subjects, and grading scales/bands. It loads actual API data, follows pagination, supports local search, create/edit, lifecycle changes, and safe activate/deactivate actions. It shows loading, empty, success, and error messages. The navigation and API both limit access to school admins, managers, and platform superadmins.

## Migrations and checks

Apply schema changes from the project root:

```powershell
.venv\Scripts\python.exe backend\manage.py migrate
```

The migration is additive and creates `academics/0001_initial.py`. It does not alter school, membership, or user rows.

### Local manual-testing accounts

After migrating, create a dedicated pair of demo schools and four testing users on the local SQLite development database:

```powershell
.venv\Scripts\python.exe backend\manage.py seed_academic_test_accounts
```

The command prints newly generated passwords once. Save them somewhere private for the manual check; they are not emailed, stored in source control, or hard-coded. Accounts are `academic-admin@edustacked.test` (school admin), `academic-manager@edustacked.test` (school manager), `academic-teacher@edustacked.test` (teacher), and `academic-outsider@edustacked.test` (admin at the separate test school). Use the teacher account for a less-privileged denial check and the outsider account for cross-school denial. The command creates schools and memberships only; it leaves academic setup empty so the checklist can create those records itself.

The seed command refuses to run unless `DEBUG=True` and the configured database engine is SQLite. Running it again does not reset existing passwords. Use `--reset-passwords` only when you intentionally want to rotate all four local demo-account passwords; the command prints the new ones.

Run the full backend suite:

```powershell
.venv\Scripts\python.exe backend\manage.py test apps.core.tests apps.accounts.tests apps.schools.tests apps.academics.tests --verbosity 1
```

Manual walkthrough: use the generated `academic-admin` account, select **EDUstacked Test School North**, and follow the checklist below. Use `academic-teacher` for the permission denial, then `academic-outsider` to try the other school. The backend API tests include the same end-to-end scenario.

1. Create the `2026/2027` academic session and its First, Second, and Third Terms with non-overlapping dates within the session.
2. Try creating the same session again; the API must reject the duplicate.
3. Create JSS 1 and SS 1. Select JSS 1 and add arms A and B (displayed together as JSS 1 A and JSS 1 B).
4. Create Mathematics and English Language, then assign both to each class. Try assigning Mathematics to JSS 1 a second time; the API must reject the duplicate.
5. Create a grading scale, add non-overlapping boundaries that cover the maximum score, then try an inverted or overlapping band. It must be rejected. The scale can be activated only after all active bands cover the range without gaps.
6. Sign in as `academic-teacher` and try to open Academic setup or submit a configuration change; access must be denied.
7. Sign in as `academic-outsider`, select **EDUstacked Test School South**, then try to retrieve an academic record from North; the API must deny the request.

## Limitations

- PostgreSQL is the deployment database, but migration application and test execution in this workspace were verified against local SQLite only unless separately reported in the completion summary.
- Grade band coverage uses an inclusive two-decimal scale; the application does not compute grades or evaluate student scores.
- The domain has no default sessions, terms, classes, subjects, or grade policy. School staff configure their own values.
