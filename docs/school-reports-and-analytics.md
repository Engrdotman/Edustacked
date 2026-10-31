# School Reports and Analytics (Module 12)

Module 12 adds school-scoped reporting over the existing source modules. Reports are read-only and do not alter enrollments, attendance, assessment results, report-card snapshots, payments, or credits. No new database tables or migrations were needed.

## Reports and metric definitions

- **Currently enrolled:** active student records with an active enrollment in the selected session. The default session is the school's active session. Historic enrollments are not included in this card.
- **Enrollment distribution:** non-pending enrollment records grouped by historical session/class/arm placement and enrollment status. Transfers remain separate placement records, preserving the original class history.
- **Admissions:** student admission dates in the selected date range, counted from the existing student record.
- **Withdrawals and transfers:** immutable enrollment records whose withdrawal or transfer dates fall in the selected date range.
- **Attendance:** explicitly marked `AttendanceRecord` rows from finalized registers only. Present and late count as attended; absent and excused count in the denominator. The percentage is `(present + late) / marked records * 100`. Missing registers and unmarked records are omitted. With no marked records, the percentage is `null` and the UI says there is no recorded data.
- **Academic performance:** per-plan average and grade distribution use `AssessmentResult.approved_percentage` and `approved_grade` for approved records only. Draft and submitted result counts are shown separately as workflow progress.
- **Report-card status:** uses the existing draft, review, approved, and finalized lifecycle; finalized means published. Expected students are non-pending enrollment records in the selected session/class/arm. Completion is `published cards / expected enrollments * 100`; a class with expected students and no cards is 0%, and a zero-enrollment class has no percentage.
- **Finance:** credit balance comes from `CreditAccount`; verified purchase revenue is the sum of successful `CreditPayment.amount_minor` values converted from kobo to NGN. Pending, failed, and reversed payments remain separately grouped. Credit movements and reconciliation issues use the existing append-only ledger and issue records. A missing credit account is shown as not configured, not as a zero balance.

The date range defaults to the active term's dates, or the last 30 days when no active term is configured. All dates use Django's school-local date handling for the default range. Session, term, class, arm, date, search, and pagination filters are validated server-side. Financial reports use the date range; academic placement filters do not apply to payments.

## Role access

| Role | Available reports |
| --- | --- |
| School admin | Enrollment, attendance, academics, report cards, and finance |
| School manager | Enrollment, attendance, academics, and report cards |
| Teacher | Attendance, academic summaries, and report-card counts limited to active assigned session/class/arm/subject scopes; no school-wide enrollment or finance reports |
| Accountant | Finance and credit reporting only |
| Receptionist/front desk | Enrollment and operational enrollment summaries |
| Parent/guardian | No school-wide reports; Module 11 continues to expose only linked children |
| Platform superuser | A selected school at a time through the existing platform authorization behavior; no tenant-wide aggregate endpoint |

Every endpoint uses authenticated school membership permissions and filters source querysets by the authorized school. Supplying an ID belonging to another school does not select that tenant. Report filters never grant access by themselves.

## API

All endpoints are under `/api/v1/reports/`. Include the selected school through the existing `X-School-ID` header. The dashboard response includes the authorized filter options and the report sections available to that role.

| Method and path | Permission |
| --- | --- |
| `GET dashboard/` | `reports.dashboard`; returns role-specific summary cards and authorized filter metadata |
| `GET enrollment/` | `reports.enrollment`; distribution, admissions, withdrawals, transfers; `view=students` adds a paginated, searchable limited roster |
| `GET attendance/` | `reports.attendance`; date/class/arm counts or `view=students` paginated marked-record summaries |
| `GET academics/` | `reports.academics`; per-plan submission progress, approved averages, and approved grade distribution |
| `GET report-cards/` | `reports.report_cards`; lifecycle counts and publication completion by class/arm |
| `GET finance/` | `reports.finance`; balances, payment states, verified purchase totals, ledger movement, and reconciliation counts |

Filters use `session`, `term`, `class_level`, `arm`, `start_date`, and `end_date`. Roster reports also support `view=students`, `search`, `page`, and `page_size`. Append `export=csv` to supported report endpoints to export the same authorized, filtered result. Finance exports include payment references only for roles that already have finance access. Exports are streamed; student exports omit guardian details and CSV formula-like cells are prefixed safely.

## Performance and limitations

Counts and summary tables use database aggregation. Attendance student summaries and enrollment rosters are paginated; CSV rows are iterated in chunks. There is no cache to risk mixing tenant-specific results, and no new indexes were added because existing attendance, enrollment, result, report-card, and ledger indexes cover the report filters. Academic comparisons across terms are not provided; only same-filter approved result summaries are shown. Student-level assessment history and automated at-risk alerts are not included in this release.

## Verification

```powershell
.venv\Scripts\python.exe backend\manage.py check
.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe backend\manage.py test apps.reports.tests --verbosity 1
.venv\Scripts\python.exe backend\manage.py test apps.core.tests apps.accounts.tests apps.schools.tests apps.academics.tests apps.students.tests apps.staff.tests apps.attendance.tests apps.results.tests apps.report_cards.tests apps.billing.tests apps.parent_portal.tests apps.reports.tests --verbosity 1
npm.cmd run build # from frontend/
```
