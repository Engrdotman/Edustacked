# Student attendance (Module 7)

Attendance is school scoped and tied to an existing academic session, term, class, arm, and student enrollment. A register is unique per school, class, arm, and date. Creating a register snapshots the students eligible on that date; later enrollment changes do not alter its roster.

## Enrollment eligibility

- Pending enrollments are never eligible.
- Active enrollments are eligible from their start date through the academic session end date.
- Completed enrollments are eligible from their start date through the session end date.
- Withdrawn enrollments are eligible through their withdrawal date, inclusive.
- A transferred enrollment remains eligible in its old class through the day before the transfer date. The new placement is eligible from its own start date.
- Dates are checked against the school's configured timezone. Future registers are rejected.

The chosen term must belong to the selected session and include the attendance date. Attendance currently uses calendar dates; there is no school-calendar/holiday or half-day model.

## Register workflow and access

Registers move through `draft` → `submitted` → `finalized`. A draft can contain unmarked roster entries, but submission requires every snapshot student to have a status. Statuses are `present`, `absent`, `late`, and `excused`. Teachers can record attendance only for classes and arms covered by an active teacher assignment. School administrators and managers can finalize or reopen a finalized register; reopening requires a reason. Finalized records cannot be edited until reopened.

Register writes are transactional and require the current register `version`. A stale version returns HTTP 409 so the client can reload before writing. The unique register constraint prevents duplicate daily registers. Register/record actor fields and immutable audit events preserve creation, corrections, submission, finalization, and reopening history. There is no hard-delete API for registers or records.

All endpoints require authentication, an explicitly selected authorized school, and the corresponding attendance permission. Receptionists and accountants have no attendance write permission. Querysets and related object validation are school scoped.

## API

Base path: `/api/v1/attendance/`.

| Endpoint | Purpose |
| --- | --- |
| `GET options/?date=YYYY-MM-DD` | Sessions, classes/arms, and terms available to the caller (teacher options are assignment scoped). |
| `GET eligible-students/?academic_session=&class_level=&class_arm=&date=` | Preview eligible enrollments, or the frozen register roster if one exists. |
| `GET registers/?date_from=&date_to=&academic_session=&class_level=&class_arm=&status=` | Paginated school/teacher scoped register list. |
| `POST registers/create/` | Create a draft and snapshot its eligible roster. Body: session, term, class, arm, and attendance date IDs/value. |
| `GET registers/{id}/` | Register, roster, and audit events. |
| `PATCH registers/{id}/records/` | Bulk save statuses/notes. Body: `{"version": 1, "records": [{"student_id": 123, "status": "present", "note": ""}]}`. |
| `PATCH records/{id}/` | Update one record using the current register version. |
| `POST registers/{id}/{submit,finalize,reopen}/` | Change register state using `{"version": 1, "reason": "..."}` (reopen requires a reason). |
| `GET students/{id}/history/` | Paginated student attendance history; finalized only by default. |
| `GET reports/summary/?date_from=&date_to=` | Attendance totals and daily counts; date ranges are capped at 366 days. |

`include_provisional=true` includes submitted registers in reports/history. Drafts are never included in reports. Reports do not infer absence when a class register is missing. The attendance percentage is `(present + late) / all recorded valid statuses × 100`; excused is included in the denominator. An empty denominator yields 0%.

## Verification and manual acceptance

Run the automated tests with:

```powershell
.venv\Scripts\python.exe backend\manage.py test apps.attendance.tests
```

The API tests cover tenant and role boundaries, teacher assignment scope, duplicate and future registers, enrollment eligibility, atomic bulk writes, optimistic concurrency, lifecycle transitions, audit history, and reporting. Also verify through the UI: create a register for an eligible class/date, mark and save statuses, submit it, finalize as an administrator, confirm finalized-only reporting, reopen with a reason, and check that a teacher cannot open another teacher's class register.
