# EDUstacked database schema (Modules 1–3)

This document describes the tenant, authentication, and school configuration schema through Module 3. Django migrations are the executable source of truth; apply them locally with `python backend/manage.py migrate`.

## Entity relationships

```mermaid
erDiagram
    USER ||--o{ SCHOOL_MEMBERSHIP : belongs_to
    SCHOOL ||--o{ SCHOOL_MEMBERSHIP : has
    SCHOOL ||--|| SCHOOL_SETTINGS : configures
    SCHOOL ||--o{ ACADEMIC_SESSION : defines
    ACADEMIC_SESSION ||--o{ TERM : contains
    SCHOOL ||--o{ CLASS_LEVEL : defines
    CLASS_LEVEL ||--o{ CLASS_ARM : groups
    CLASS_LEVEL ||--o{ CLASS_SUBJECT : assigns
    SUBJECT ||--o{ CLASS_SUBJECT : assigned
    SCHOOL ||--o{ GRADING_SCALE : configures
    GRADING_SCALE ||--o{ GRADE_BAND : contains

    USER {
        bigint id PK
        string username UK
        string email
        string login_email UK
        boolean is_active
        datetime created_at
        datetime updated_at
    }
    SCHOOL {
        bigint id PK
        string name
        string slug UK
        string contact_email
        string contact_phone
        text address
        string logo
        string state
        string local_government_area
        string website
        string motto
        text description
        boolean is_active
        datetime created_at
        datetime updated_at
    }
    SCHOOL_MEMBERSHIP {
        bigint id PK
        bigint user_id FK
        bigint school_id FK
        string role
        boolean is_active
        datetime created_at
    }
    SCHOOL_SETTINGS {
        bigint id PK
        bigint school_id FK_UK
        string default_currency
        string time_zone
        string date_format
        string academic_year_label
        json contact_preferences
        string branding_primary_color
        datetime created_at
        datetime updated_at
    }
    ACADEMIC_SESSION {
        bigint id PK
        bigint school_id FK
        string name
        date start_date
        date end_date
        string status
        datetime created_at
        datetime updated_at
    }
    TERM {
        bigint id PK
        bigint school_id FK
        bigint academic_session_id FK
        string name
        smallint sequence
        date start_date
        date end_date
        string status
    }
    CLASS_LEVEL {
        bigint id PK
        bigint school_id FK
        string name
        string code
        string category
        boolean is_active
    }
    CLASS_ARM {
        bigint id PK
        bigint school_id FK
        bigint class_level_id FK
        string name
        boolean is_active
    }
    SUBJECT {
        bigint id PK
        bigint school_id FK
        string name
        string code
        boolean is_active
    }
    CLASS_SUBJECT {
        bigint id PK
        bigint school_id FK
        bigint class_level_id FK
        bigint subject_id FK
        boolean is_active
    }
    GRADING_SCALE {
        bigint id PK
        bigint school_id FK
        string name
        decimal maximum_score
        boolean is_active
    }
    GRADE_BAND {
        bigint id PK
        bigint school_id FK
        bigint grading_scale_id FK
        string label
        decimal min_score
        decimal max_score
        decimal grade_point
        boolean is_active
    }
```

`USER` is the custom Django `accounts.User` model derived from `AbstractUser`. `username` remains for Django admin compatibility; normalized `login_email` is the unique email sign-in identity. A user can belong to multiple schools, and a school can have multiple users, through `SchoolMembership`.

## Module 7: attendance tables

The attendance migration is `backend/apps/attendance/migrations/0001_initial.py`.

### `attendance_attendanceregister`

- Links one school, academic session, term, class, arm, and attendance date. A database unique constraint allows one register per school/class/arm/date.
- `status` is `draft`, `submitted`, or `finalized`. `version` increments on writes and state changes for optimistic concurrency.
- Actor foreign keys record who created, submitted, finalized, or reopened the register. Registers cannot be deleted through the application model/API.

### `attendance_attendancerecord`

- One row per student in the enrollment snapshot, with foreign keys to the register and the qualifying enrollment. A unique register/student constraint prevents duplicate roster rows.
- `status` is nullable only while a snapshot student remains unmarked in a draft. Valid marked statuses are `present`, `absent`, `late`, and `excused`.
- `recorded_by` and `last_modified_by` capture the record actors. Register/student/enrollment identity is immutable after snapshot creation.

### `attendance_attendanceauditevent`

- Append-only state and record change history with actor, event type, old/new status, reason, and timestamp. Model validation blocks updates and deletes.

See [student-attendance.md](student-attendance.md) for the eligibility, API, reporting, and verification rules.

## Module 8: assessments and results tables

The results migration is `backend/apps/results/migrations/0001_initial.py`.

- `results_assessmentcomponent` stores school-level reusable templates. Plan-specific maxima and weights are copied into `results_plancomponent`.
- `results_assessmentplan` links the existing academic session, term, class, arm, subject, and grading scale. Its grading maximum and active grade bands are stored in `grading_scale_snapshot` JSON so later scale edits do not rewrite old results.
- `results_assessmentresult` is unique per plan/student and links the matching enrollment. It stores workflow state, concurrency version, and approved total, percentage, grade, grade point, and calculation snapshot.
- `results_componentscore` stores decimal marks and entry/last-modification actors, unique per result/component.
- `results_resultauditevent` is append-only and records score values, state changes, actors, reasons, and timestamps.

See [assessment-results.md](assessment-results.md) for calculation, lifecycle, API, permission, and migration details.

## Module 9: report-card tables

The report-card migration is `backend/apps/report_cards/migrations/0001_initial.py`.

- `report_cards_reportcard` binds one report to a school, student, historical enrollment, academic session, term, class, and arm. A unique constraint prevents duplicate student/enrollment/session/term report cards.
- `report_cards_reportcardrevision` stores the mutable draft/review/approved revision and immutable finalized snapshots as JSON, with generated/reviewed/approved/finalized actors and timestamps.
- `report_cards_reportcardauditevent` stores append-only lifecycle actions, actor, reason, and metadata.

See [report-cards.md](report-cards.md) for source validation, PDF, workflow, and API details.

## Tables and integrity rules

### `schools_school`

- `id`: Django `BigAutoField` primary key and unique school identifier.
- `name`: required, up to 200 characters.
- `slug`: required, unique, up to 220 characters; generated from the school name when omitted.
- `contact_email`: optional email address.
- `contact_phone`: optional phone number, up to 30 characters.
- `address`: optional text.
- `logo`: optional `ImageField` stored under a generated per-school filename; files are served through an authenticated school-scoped API endpoint.
- `state`, `local_government_area`, `website`, `motto`, `description`: optional profile fields.
- `is_active`: boolean, defaults to true.
- `created_at`, `updated_at`: creation and last-update timestamps.
- Database checks reject an empty name or slug. The unique slug constraint prevents duplicate school codes.

### `accounts_user`

- Extends Django's `AbstractUser`: username, password hash, names, `is_active`, staff/superuser flags, and Django authentication relations.
- `email`: retained for account contact and compatibility.
- `login_email`: nullable unique normalized email used by the authentication API. New accounts must have one. A migration fills it only for existing email addresses that are nonblank and unambiguous; legacy blank or duplicate email accounts remain intact and need an administrator to correct the email before email login/reset is available.
- `created_at`, `updated_at`: account timestamps.
- Passwords are stored only as Django password hashes.

### `schools_schoolmembership`

- `id`: `BigAutoField` primary key.
- `user_id`: required foreign key to `accounts_user`, cascades on user deletion.
- `school_id`: required foreign key to `schools_school`, cascades on school deletion.
- `role`: `school_admin`, `school_manager`, `teacher`, `accountant`, `receptionist`, or legacy `member`. The default `member` has no permissions. Platform superadmins are Django `is_superuser` accounts, not a school membership role.
- `is_active`: boolean, defaults to true; inactive memberships grant no tenant access.
- `created_at`: membership creation timestamp.
- A unique constraint permits only one membership per user-school pair.
- A database check constraint limits role values to the declared choices. The migration maps legacy `owner` and `admin` to `school_admin`; legacy `member` remains permissionless.
- An index on `(user_id, is_active)` supports resolving a user's active memberships; foreign key and unique constraints provide their own supporting indexes.

### `schools_schoolsettings`

- One-to-one relationship to `schools_school`; deleting a school cascades to its settings.
- `default_currency`: three-letter ISO-style code, default `NGN`.
- `time_zone`: IANA time-zone name, default `Africa/Lagos`.
- `date_format`: one of `DD/MM/YYYY`, `MM/DD/YYYY`, or `YYYY-MM-DD`.
- `academic_year_label`: display label only; no academic sessions or terms are stored here.
- `contact_preferences`: JSON object of email/phone boolean preferences.
- `branding_primary_color`: six-digit hex color, default `#285744`.
- `created_at`, `updated_at`: settings timestamps.
- New schools receive a default settings row; migration `schools/0007_*` initializes existing schools.

## Academic configuration tables (Module 4)

All eight academic models belong to `apps.academics`. Every table has a `BigAutoField` primary key and a required school foreign key. Academic sessions, terms, classes, class arms, subjects, class-subject assignments, grading scales, and grade bands are configuration only; there are no student, enrollment, assessment, attendance, result, or report-card tables in this module.

- `academics_academicsession`: case-insensitive unique session name per school, ordered date check, conditional unique constraint for one active session per school. Lifecycle starts at draft; transitions draft → active → completed. Active details are locked and completed sessions are immutable.
- `academics_term`: session and school foreign keys, unique case-insensitive name and sequence per session, date-order check, one active term per session. Model validation enforces same-school parent, dates inside the session, and non-overlap. Terms transition draft → active → completed.
- `academics_classlevel`: school-specific class name and optional code are unique case-insensitively per school. Inactive classes are retained.
- `academics_classarm`: school and protected class-level foreign keys; arm names are unique case-insensitively within the class. Parent-school consistency is validated before save.
- `academics_subject`: school-specific case-insensitive name and optional code uniqueness. Inactive subjects are retained.
- `academics_classsubject`: class/subject pair uniqueness plus school consistency validation. Class and subject foreign keys use `PROTECT`.
- `academics_gradingscale`: school-specific case-insensitive name, positive configurable maximum, and active state. A scale may be activated only when its active bands cover 0.00 through its maximum with contiguous hundredth increments.
- `academics_gradeband`: decimal score boundaries and optional grade point, nonnegative and ordered checks, unique case-insensitive label per scale, no active overlaps, parent-school consistency. Grade-band and grading-scale links use `PROTECT` so future result records can preserve their grading definition.

Lowercase functional unique constraints prevent case-only duplicate names/codes in PostgreSQL and SQLite. Model/serializer validation enforces cross-table invariants that ordinary portable database constraints cannot express.

## Tenant-owned records in later modules

Module 1 does not create student, staff, class, fee, attendance, or result tables. Each such model must add a required foreign key to `schools_school`. Its API must resolve the school through the authenticated user's active membership and apply that school to all reads and writes. See [architecture.md](architecture.md) for the reusable queryset mixin and required tenant-isolation tests.

## Student management tables (Module 5)

All student tables are in `apps.students` and carry a required school foreign key. Student class placement belongs to the enrollment row, so students retain their identity when moving between classes or sessions.

- `students_student`: school-scoped case-insensitive admission number; name, optional date of birth/gender/contact/address/photo; admission date; active/inactive status; timestamps. Admission number and school are immutable after creation. No uniqueness constraint is placed on name or date of birth.
- `students_guardian`: school-scoped name, phone, email, address, active flag, and timestamps. A guardian can link to multiple siblings within one school.
- `students_studentguardian`: student/guardian association, relationship type, primary/emergency/communication flags, active flag, timestamps; unique student/guardian pair and at most one active primary contact per student. Model validation enforces same-school links.
- `students_studentenrollment`: school, student, academic session, class level, and arm; enrollment date and pending/active/completed/withdrawn/transferred state; withdrawal/transfer metadata; optional previous-enrollment link for transfer history; timestamps. Conditional uniqueness prevents multiple current enrollments in one session, while historical rows are retained.

Student records are deactivated rather than deleted. Transfer changes the old active enrollment to transferred and creates a successor in one transaction. Photos are optional, size/format validated, stored under generated names, and streamed through an authenticated school-scoped endpoint. Migration `students/0001_initial` creates the Module 5 schema.

## Staff and teacher assignment tables (Module 6)

All staff records belong to a school and are separate from authentication accounts. `staff_staffprofile` stores staff number (case-insensitive unique per school), optional existing User link, job and employment dates/type/status, optional work contact/photo, and timestamps. The optional user link is unique per school and is validated against an existing active school membership; linking does not provision membership or privileges. `staff_teacherprofile` designates a staff profile as a teacher and stores optional qualification summary/specialization and teaching status.

`staff_teacherassignment` stores one explicit teaching responsibility per row: teacher, academic session, class, arm, subject, start/end dates, and optional replacement reason. Conditional uniqueness prevents duplicate active responsibility for the same teacher/session/class/arm/subject. A self-link records replacement history. Status transitions are active to ended/cancelled; ended/cancelled assignments cannot be reactivated. Employment or teaching deactivation ends current assignments and retains history. Migrations `staff/0001_initial` and `staff/0002_teacherassignment_change_reason` create Module 6 tables and fields.

## Migrations

## Report-card credits and payments (Module 10)

`billing_creditaccount` stores one cached nonnegative balance per school. `billing_creditpackage` stores admin-configured NGN kobo price, credits, active state, description, and display order. `billing_creditpayment` stores the school, price/credit snapshots, internal/provider reference, status, checkout URL, and verification metadata. `billing_credittransaction` is the signed append-only ledger with an idempotency reference, optional payment or report-card billing link, actor, and metadata. `billing_reportcardbilling` uniquely records school/student/session/term, linking to the report card and finalized revision. `billing_reconciliationissue` tracks mismatched or reversed provider events and their resolution notes. Migrations `billing/0001_initial` and `billing/0002_grandfather_existing_finalized_cards` create the models and record previously finalized periods without retroactive charges.

## Parent/guardian portal (Module 11)

The existing `students_guardian` table adds a nullable `user_id` foreign key to the existing account table; active `students_studentguardian` rows remain the source of student access. `parent_portal_guardianinvitation` stores only a token hash and the invitation lifecycle. `parent_portal_announcement` stores school-scoped staff announcements and publication/expiry state. `parent_portal_portalnotification` stores recipient-specific, idempotent event notifications. `parent_portal_portalauditevent` stores append-only portal security events. See [parent-guardian-portal.md](parent-guardian-portal.md) for lifecycle and endpoint details. Additive migrations are `students/0002_guardian_user` and `parent_portal/0001_initial`.

## School reporting and analytics (Module 12)

Module 12 adds the `apps.reports` query/service and API layer without introducing persistent models. Reports aggregate the existing school-scoped source tables and require no schema migration. Metric formulas, role permissions, filters, and export behavior are described in [school-reports-and-analytics.md](school-reports-and-analytics.md).

- `accounts/0001_initial` and `0002_*`: custom user model, normalized email login identity, and timestamps.
- `schools/0001_initial` and later migrations: school identity, memberships, roles, school profile fields, protected logo metadata, and one-to-one school settings.
- `academics/0001_initial`: session, term, class, arm, subject, assignment, grading scale, and grade band tables and database constraints.
- `token_blacklist/*`: Simple JWT outstanding and revoked refresh-token records.
- School migrations add fields and constraints without replacing the existing school primary key or deleting users.
