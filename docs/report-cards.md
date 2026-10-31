# Report cards (Module 9)

Report cards use the existing enrollment, class-subject mapping, assessment plans and approved result snapshots, grading snapshots, school profile/settings, and finalized attendance registers. No credit, billing, payment, or parent portal behavior is included.

## Generation and validation

Generate for one enrollment/term or a class/arm/session/term. Generation creates or refreshes a draft revision and returns actionable validation errors. A term must belong to the student's enrollment session and school. The enrollment must belong to the selected school/student/session/class/arm and overlap the term.

Every active subject assigned to the class is required. Each subject must have exactly one approved result for the student, enrollment, session, term, class, and arm. Multiple approved plans for the same subject are currently blocked with a validation message: the source modules do not define how separate term assessments should be combined into one subject mark, so the report-card module does not invent a formula. Missing or unapproved results are never converted into zero.

Report cards copy the approved result's saved component calculations, total, maximum, percentage, grade, grade point, and plan grading-scale snapshot. They do not independently recalculate grades. School/student/session/term/class display values, remarks, attendance totals, and configured logo path are stored in the report revision snapshot. Overall totals, averages, class positions, conduct, effort, teacher remarks, and sign-off names are omitted/blank unless authorized staff supply the optional remarks and names. No signature is represented as signed.

Attendance uses only finalized Module 7 records whose exact enrollment is linked to a register date within the term. Present and late count as attended; all recorded statuses including absent and excused are in the denominator. Attendance percentage is unavailable when no finalized record exists. Missing registers are excluded and never treated as absence.

Before review and again before finalization, current source values are compared to the generated snapshot. If enrollment, school profile, approved results, grading snapshot, or finalized attendance has changed, review/finalization is blocked until an authorized user regenerates the draft. Published snapshots remain immutable. A correction action on a finalized report starts a new draft revision with a required reason and preserves the prior official revision and its PDF data.

## Lifecycle and access

`draft → review → approved → finalized`. Managers and school administrators can generate and submit reports for review. School administrators and platform superadmins can approve and finalize. Authorized reviewers may return review/approved drafts for correction with a reason. Only an administrator/superadmin may start a correction revision from an official finalized card. Accountants and receptionists have no report-card access. Teachers can read cards for their assigned class, arm, and session; each teacher response/PDF only exposes subjects assigned to that teacher. Other school data is tenant scoped by membership and queryset.

The single finalization boundary is `apps.report_cards.services.finalize_report_card`. Module 10 can add credit validation and consumption there. Preview, download, and reprint do not change state and do not charge credits.

## PDF

PDFs are rendered on the backend with ReportLab as A4 documents, with repeating academic table headers, school color/logo where available, student and academic details, component marks, grades, finalized attendance, remarks, and unsigned sign-off lines. PDFs are generated from the selected saved revision and require authenticated, school-scoped API access. The school logo is referenced by its storage path in the snapshot; the project's current local/private media storage policy applies. Filename pattern: `{report identifier}-{student surname}-v{revision}.pdf`.

Install requirements using the existing backend requirements file, which includes `reportlab>=4.2,<5`.

## API

Base prefix: `/api/v1/`; selected school authorization uses the existing `X-School-ID` context.

| Endpoint | Purpose |
| --- | --- |
| `GET report-cards/` | Paginated listing. Filters: `academic_session`, `term`, `class_level`, `class_arm`, `status`, and `search`. |
| `POST report-cards/generate/` | Generate/refresh one draft. Body: `{"enrollment": 31, "term": 4}`. Returns the report, validation errors, and whether it is actionable. |
| `POST report-cards/generate-class/` | Generate drafts for eligible class/arm students. Body: `{"academic_session": 2, "term": 4, "class_level": 5, "class_arm": 9}`. Each student succeeds/fails independently and receives validation details. |
| `GET report-cards/{id}/` | Detail, current revision snapshot, revisions, and audit trail. |
| `PATCH report-cards/{id}/` | Draft remarks and sign-off display names only. |
| `POST report-cards/{id}/review/` | Validate source freshness/completeness and submit draft for review. |
| `POST report-cards/{id}/approve/` | Approve a reviewed revision (admin/superadmin). |
| `POST report-cards/{id}/finalize/` | Publish through the backend finalization service (admin/superadmin). |
| `POST report-cards/{id}/return/` | Return an unfinalized reviewed card with `{"reason": "..."}`. |
| `POST report-cards/{id}/correct/` | Create a new correction draft from finalized card with a required reason. |
| `GET report-cards/{id}/pdf/?preview=true` | Authenticated inline PDF preview. |
| `GET report-cards/{id}/pdf/` | Download/reprint the newest finalized revision (or current draft when not finalized). `?revision={revision_id}` selects a saved revision. |

Audit events are append-only and record generation, review, approval, finalization, return, remarks update, and correction-revision creation. Every finalized revision is immutable. A uniqueness constraint prevents duplicate cards for the same school/student/enrollment/session/term.

## Verification

```powershell
.venv\Scripts\python.exe backend\manage.py migrate
.venv\Scripts\python.exe backend\manage.py test apps.report_cards.tests
```

The Module 9 API tests exercise approved-result generation, grades/totals, finalized-only attendance, incomplete source blocking, class generation, duplicate prevention, lifecycle authorization, PDF output/access, immutable finalized snapshots, correction revisions, teacher subject scope, and tenant isolation.

No frontend test runner is configured in the repository. The production Vite build is the available frontend check; interactive browser verification should follow the manual sequence above.
