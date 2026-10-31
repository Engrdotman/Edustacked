# Assessments and results (Module 8)

Module 8 adds school-scoped assessment plans and per-student result approval. It reuses academic sessions, terms, classes, arms, subjects, grading scales, enrollments, teacher assignments, and school memberships. Report-card generation, report-card versions/PDFs, credits, billing, and payments are outside this module.

## Data model and configuration

- `AssessmentComponent` is a reusable school-level template with a suggested maximum mark and optional default weight. Editing a template does not alter any existing plan.
- `AssessmentPlan` joins a session, term, class, arm, subject, active grading scale, assessment name, and calculation method. One case-insensitive plan name is allowed per school/term/arm/subject. Every relationship is checked against the tenant; arms must belong to the selected class, terms to the session, and configured class subjects must include the chosen subject.
- `PlanComponent` snapshots its own maximum marks and optional weight. Plan components cannot be edited after score entry begins, or after publication. Raw plan maxima must add exactly to the grading scale maximum. Weighted components must each have a positive weight and weights must total exactly 100.00%; no normalization occurs.
- The grading-scale maximum and active grade bands are snapshotted into the plan on creation. Future changes to the source scale/bands do not silently recalculate already approved results.
- `AssessmentResult` is one student's result for one plan. It links the student's eligible enrollment and holds a draft/submitted/approved lifecycle. `ComponentScore` stores numeric marks and entry actors. `ResultAuditEvent` is append-only and records score changes, submission, approval, reopening, and plan lifecycle events.

## Enrollment and missing-score policy

The plan roster includes active or completed enrollments that started by the term end, plus withdrawn/transferred enrollment history whose withdrawal/transfer date falls on or after the term start. The enrollment must match the school's session, class, and arm. Pending enrollments are excluded. A student without a result remains without a result; the system does not create zero marks or infer absence. All configured component marks are required before a result can be submitted. This module has no excused/absent score outcome; schools must follow their own documented assessment policy before an authorized user enters a numeric mark.

## Calculation and rounding

All authoritative calculations use `Decimal` and round to two decimal places using `ROUND_HALF_UP`.

- Raw mode: `calculated_total = sum(component scores)` and `calculated_maximum = sum(component maxima)`. Publication requires the component maximum total to equal the grading scale maximum.
- Weighted mode: each component contributes `(score / component maximum) × component weight`. Weights must total 100%. The resulting percentage is mapped to the grading scale's configured maximum.
- Percentage is `calculated_total / calculated_maximum × 100`. The rounded result score is matched against the plan's snapshotted grade bands, inclusive at each boundary. Grade points are copied from those bands.
- Partial results show entered component totals but have no authoritative percentage or grade. They cannot be submitted or approved.

## Workflow and permissions

Assessment plans move from `draft` to `published` to `closed`. Administrators and managers with academic management permission configure components and plans, publish them, close them, and reopen closed plans with a reason. Closing requires an approved result for every currently eligible student. Teachers can enter and submit drafts only for a matching active assignment (teacher, session, class, arm, and subject whose dates overlap the term). A result is approved **per student**, by a school administrator or platform superadmin. A plan creator or score recorder cannot approve that result. Managers cannot approve by default. Reopening an approved result requires an approver and a reason; its former approved snapshot and audit events remain available while the result returns to draft for correction.

Accountants and receptionists have no result permissions. All API querysets and relationship validators are school scoped; API writes are validated server-side. Score entry is atomic across a batch, carries per-result versions, locks the plan/results during a write, and returns HTTP 409 for stale versions. Submitted and approved results are protected from score edits.

## API

Base path: `/api/v1/` and the selected school must be supplied using the existing school-selection context/header.

| Endpoint | Purpose |
| --- | --- |
| `GET/POST assessment-components/` | List or create reusable school-level component templates (management roles). |
| `GET/PATCH assessment-components/{id}/` | Read or update a template. Used templates are deactivated instead of deleted. |
| `GET/POST assessment-plans/` | List plans (filterable by `academic_session`, `term`, `class_level`, `class_arm`, `subject`, `status`) or create a draft. |
| `GET/PATCH assessment-plans/{id}/` | Read or update a draft plan before scores are entered. |
| `GET/POST assessment-plans/{id}/components/` | List or add component snapshots. Create body: `{"component": 3, "max_score": "20.00", "weight": "20.00", "position": 1}`. |
| `PATCH/DELETE assessment-plans/{id}/components/{component_id}/` | Update/remove a draft component before score entry. |
| `POST assessment-plans/{id}/publish/` | Publish a draft using `{"version": 2}` after component totals/weights validate. |
| `POST assessment-plans/{id}/close/` | Close after every eligible student's result is approved. Requires current plan version. |
| `POST assessment-plans/{id}/reopen/` | Reopen a closed plan with current `version` and a reason. |
| `GET assessment-plans/{id}/eligible-students/` | Paginated eligible roster. |
| `GET/PATCH assessment-plans/{id}/results/` | Paginated roster/results or atomically save scores. |
| `POST assessment-plans/{id}/results/submit/` | Submit one or more complete student results with student IDs and result versions. |
| `POST assessment-plans/{id}/results/approve/` | Approve submitted student results (administrator/superadmin, no self-approval). |
| `POST assessment-plans/{id}/results/reopen/` | Reopen approved results with reason and versions. |
| `GET assessment-results/` | Paginated result filter by session, term, class, arm, subject, assessment, student, or status. |
| `GET assessment-results/{id}/` | Result, server calculation, approved snapshot, component scores, and audit history. |

Score entry example:

```json
{
  "entries": [
    {"student_id": 123, "version": 0, "scores": [
      {"plan_component_id": 10, "score": "18.50"},
      {"plan_component_id": 11, "score": "64.00"}
    ]}
  ]
}
```

The first save uses version `0` when a result does not exist. Subsequent saves use the version returned by the results endpoint. Submission/approval actions accept `{ "entries": [{"student_id": 123, "version": 2}] }`; reopening also requires a `reason`.

## Migration, tests, and manual verification

```powershell
.venv\Scripts\python.exe backend\manage.py migrate
.venv\Scripts\python.exe backend\manage.py test apps.results.tests
```

The API tests cover component validation, tenant and assignment scope, duplicate plans, raw and weighted calculation, missing-score behavior, atomic batch rollback, score bounds, stale versions, configuration locks, submission, approval restrictions, correction reasons, immutable approved snapshots, and audit history. Full regression runs should include `apps.core.tests apps.accounts.tests apps.schools.tests apps.academics.tests apps.students.tests apps.staff.tests apps.attendance.tests apps.results.tests`.

Manual check: create (or select) an active grading scale; make a plan for an assigned subject/class/arm/session/term; configure components whose raw maxima equal the scale maximum or weighted values total 100%; publish; enter component marks as the assigned teacher; confirm partial results have no grade; complete and submit; approve as a different school administrator; confirm actor/history and the saved grade; reopen with a reason, correct a score, and submit/approve again. Verify a manager, accountant, receptionist, unassigned teacher, and other-school user cannot perform restricted actions.
