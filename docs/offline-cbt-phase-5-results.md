# EDUstacked Offline CBT Phase 5: Results and Analytics

Phase 5 takes immutable submissions synchronized from a school's LAN CBT server and creates a tenant-scoped central result. Objective questions are automatically scored against the published examination snapshot. Text responses that contain an answer remain pending until a staff member grades them; blank text answers receive zero automatically. Correctness, answer keys, and explanations are withheld in the result detail until the examination's scheduled end time.

## Deployment and setup

1. Configure `CBT_PACKAGE_SIGNING_KEY` and `CBT_LICENSE_SIGNING_KEY` on the central API and trusted local servers. Keep both secrets out of browser code and source control. The package key must be the same at the central and local endpoints.
2. Deploy the central Django service and migrate: `python manage.py migrate`. Phase 5 adds `CbtResult` and append-only `CbtResultCorrection` records.
3. Ensure the school has an active Offline CBT entitlement, publish an exam, assign actively enrolled students, export/import its signed package, and synchronize submissions from the local outbox.
4. Staff with `cbt.results.view` can inspect results and analytics. Only staff with `cbt.results.manage` can enter or correct marks. Teachers only see results for active teacher assignments matching session, class, arm, and subject. The result views require the active Offline CBT entitlement.

## Central API

All routes are under `/api/v1/` and require authenticated school context:

- `GET /cbt/results/` — paginated attempts, KPI summaries, filters, and analytics.
- `GET /cbt/results/{result_id}/` — student result and question-level review. Correct answers and explanations are released only at or after the scheduled exam end.
- `POST /cbt/results/{result_id}/corrections/` — enter/correct question marks with a required reason. Each change records the actor and before/after mark details.
- `GET /cbt/results/export/` — CSV export using the same tenant, teacher, and filter scope.
- `POST /cbt/sync/ingest/` — signed local-server submission ingest; accepted submissions create results idempotently.

Dashboard filters include academic session, term, class, subject, examination, student, and submitted date range. Analytics include participation, pass/fail, score distribution, class/subject/exam averages, monthly trend, and question-level incorrect/unanswered rates. Small samples are flagged. CSV export includes the per-attempt summary.

## Marking behavior

- Single-choice and multiple-answer responses use exact matching against frozen answer keys; partial credit is not currently supported.
- Missing objective responses count as unanswered and score zero.
- Answered text questions are not guessed or auto-scored. They stay in `needs_marking` until an authorized reviewer enters the mark.
- Blank text questions are automatically scored zero.
- Final percentage and pass/fail use the examination's pass mark copied onto the result at calculation time. Corrections re-evaluate totals using that same snapshot.
- Question review displays answer choice text, not internal option identifiers. The key is released after the exam window ends.
- Result and correction records cannot be edited/deleted through normal model saves; corrections append an audit entry and update the result snapshot atomically.

## UI walkthrough

Open **Offline CBT results** from the school dashboard (or `/app/cbt/results`). Filter attempts, review analytics, export CSV, and select a learner for the individual result. A manager/principal/admin can grade pending text responses and save corrections with a reason. The **CBT setup** link goes to `/app/cbt` for question bank and examination management.

For a manual end-to-end check, create a published exam containing one objective and one text question, assign an active student, import the package on the local server, submit one response to each, and run the outbox sync worker. Verify the objective score appears while the essay is pending, then enter the essay mark with a reason and confirm the final score, pass/fail, correction history, and CSV export. Verify a teacher only sees their assigned class/arm/subject and another school's user cannot retrieve the result ID.

## Scope and limitations

- The dashboard's pending-sync count reflects conflicts and accepted central sync events that have not produced results. It cannot count submissions still sitting only in an offline server's unsynchronized outbox.
- Results are staff-facing; this phase does not expose scores to local students, parents, or report cards.
- Objective marking is all-or-nothing. Partial-credit rules, configurable grade bands, and school-specific result approval are not included.
- The monthly trend requires at least two months of finalized results; small samples should not be treated as stable performance estimates.
- The implementation has unit/API coverage but has not been load-tested with concurrent school exam traffic.
