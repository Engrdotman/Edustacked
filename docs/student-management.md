# Student management and enrollment (Module 5)

Module 5 adds school-scoped student identities, guardian links, enrollment history, admission workflows, and a student management screen. A student can be admitted without immediate enrollment. Placement is recorded on enrollment rows so transfers preserve the prior class and dates.

## API outline

All endpoints require an authenticated user and an authorized active school, selected with `X-School-ID` or the supported school URL context.

- `GET/POST /api/v1/students/`: list/search and standalone student creation. List filters include `search`, `status`, `academic_session`, `class_level`, and `class_arm`; results are paginated.
- `POST /api/v1/admissions/`: atomically creates a student with optional new guardian links and optional initial enrollment.
- `GET/PATCH /api/v1/students/{id}/`: view or edit a student; deactivation is `PATCH {"status":"inactive"}`.
- `GET/POST /api/v1/guardians/`, `GET/PATCH /api/v1/guardians/{id}/`: manage school guardian contacts.
- `GET/POST /api/v1/students/{id}/guardians/` and `GET/PATCH/DELETE /api/v1/students/{id}/guardians/{link_id}/`: link guardians, including one guardian shared by siblings. Delete deactivates the link.
- `GET/POST /api/v1/students/{id}/enrollments/`: inspect enrollment history or add a first enrollment in a session.
- `GET /api/v1/enrollments/{id}/`; `POST /api/v1/enrollments/{id}/transition/` for workflow state changes; `POST /api/v1/enrollments/{id}/transfer/` to atomically close the active placement and create a successor row.
- `GET/POST /api/v1/students/{id}/photo/`: authenticated private photo retrieval/upload. Accepted formats are JPG, PNG, and WebP up to 2 MB.

School admins and managers can manage student records and enrollment. Receptionists can admit/enroll students and manage guardian contacts, but cannot edit/deactivate student profiles. Teachers can read a minimal roster projection without contact, birth-date, address, or photo details. Accountants and ordinary members receive no student permission. School membership and school-scoped querysets are checked on each request.

## Local acceptance accounts

After migrations on the local SQLite development database, run:

```powershell
.venv\Scripts\python.exe backend\manage.py seed_academic_test_accounts
```

It now provisions North and South test schools plus admin, manager, teacher, receptionist, accountant, and other-school admin accounts. New passwords are generated and printed at first seed; store them privately. Existing passwords remain unchanged unless `--reset-passwords` is supplied. The command refuses to run when `DEBUG` is off or the default database is not SQLite.

## Manual checklist

1. Sign in as the school admin at EDUstacked Test School North. Create a student with an admission number and optional guardian without selecting a class; verify the record appears in search.
2. Admit another student with a guardian and select the `2026/2027` session, class, and arm. Confirm the guardian and pending enrollment appear in the profile.
3. Submit a duplicate admission number using different letter case; it must be rejected. Same-name students with distinct admission numbers must be allowed.
4. Link one guardian to a second student as a sibling. Try linking the same guardian twice to one student and setting two active primary guardians; both must be rejected.
5. Add another enrollment in the same session and verify it is rejected. Transfer an active student to another class/arm; verify the old enrollment is marked transferred and the new row points to the old row. Try an invalid destination arm and verify the old enrollment remains active.
6. Deactivate a student and verify the record and enrollment history remain available, while a new enrollment is denied.
7. Sign in as `academic-receptionist`: admit a student and manage guardian links, then try changing the student status and verify access is denied. Sign in as `academic-teacher`: view the roster and verify private fields are absent; try admission, guardian data, and editing and verify denial. Sign in as `academic-accountant` and verify student access is denied.
8. Sign in as `academic-outsider` at EDUstacked Test School South and try to retrieve North student, guardian, and enrollment IDs; each request must return not found or denied without leaking record contents.
9. Upload a valid photo, then try an oversized or unsupported file. Verify only authorized users can stream it and no public media URL is exposed.

## Automated checks

Run the Module 5 tests with:

```powershell
.venv\Scripts\python.exe backend\manage.py test apps.students.tests --verbosity 1
```

The tests cover atomic admission rollback, duplicate admission numbers, school isolation, role-specific projections, sibling guardian links, duplicate links, and transfer history/rollback. The full regression suite also runs Modules 1–4.
