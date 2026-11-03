# EDUstacked platform acceptance run

- **Run date:** 2026-11-03
- **Environment:** local development SQLite database; EDUstacked North demo school
- **Scope:** teacher/admin API workflows, student enrollment, attendance, assessments, report-card PDF, OCBT regression, and frontend production compilation.

## Workflow exercised with demo accounts

- Signed in through the application login API as the existing school administrator, manager, and teacher accounts. Added the active teacher account to the school's staff directory and designated the existing second teacher profile.
- The second QA teacher account was unverified before the run. Its test password and verification timestamp were temporarily set only in the local SQLite database to exercise teacher login, then its original password hash and unverified state were restored. It cannot sign in in its current state until the normal email-verification step is completed.
- Admitted and actively enrolled four clearly marked `QA-RIGID-2026-*` students in the 2026/2027 session and existing nursery / QA-A class. The student detail API reported `current_enrollment_status: active` for each.
- Configured six QA subjects and assigned them across two teacher profiles. The demo class already had a seventh active subject (`english lang`), so it was also assigned, assessed, and included to meet report-card completeness rules.
- Took attendance as a teacher for the entire eligible class roster, including one pre-existing demo enrollee; submitted as teacher and finalized as administrator.
- Created and published seven assessment plans. Teachers entered scores for each of the four new students under their assigned subjects; an administrator approved all 28 student-subject results.
- Generated, reviewed, and approved four report cards. The rendered one-page PDF was visually inspected. It contains the full seven-subject table and finalized attendance.
- Tried to finalize a report card. The request was correctly denied because the demo school's report-card credit balance is zero. No payment or credit was fabricated.

The QA students, academic setup, attendance register, assessment plans/results, and approved report cards remain in the local demo database for review. The generated PDF is an **approved preview, not an official finalized report card**.

## Issues found and corrected

1. **Frontend production build failure:** `ServicesPage` imported `getServicePlans`, which was missing from `frontend/src/services/api.js`. Added the API wrapper. Production build now succeeds.
2. **Long report-card labels collided in the PDF:** long subject names ran into the component column. Converted subject/component cells to wrapping ReportLab paragraphs, centered numeric columns, and added a long-label regression test. The regenerated PDF was rendered and visually checked.
3. **Assessment concurrency contract:** publishing a plan with the version from before component creation correctly returned HTTP 409. The plan version increments when components are changed; refreshing the plan before publishing resolves this expected stale-version response.
4. **Incomplete existing curriculum:** the demo class already had a seventh subject, and report-card validation correctly rejected cards until that subject also had approved results. Added assessment coverage for that subject; all four report cards then passed validation.

## Verification results

- Full central Django application suite: **136 tests passed, 1 skipped**; Django system checks clean, including the report-card long-label regression test.
- Report-card suite after PDF layout changes: **6 tests passed**, including the long-label PDF case.
- Local OCBT server suite: **16 tests passed**; Django system checks clean.
- Frontend Vite production build: **passed**. Vite warns that the main JavaScript chunk is 509 KB minified; consider code splitting to reduce initial download size.
- `git diff --check`: passed. The frontend package has no automated `test` script.

## OCBT access and production-readiness limits

The existing local database contains **no service entitlements for any school**, so there was no already-granted school account to exercise end to end without inventing a grant. Central entitlement/license authorization, CBT exam/package/sync/results behavior, and local license import/expiry/renewal were covered by the 22 central CBT/entitlement tests and 16 local-server tests. The QA demo school remains unlicensed for OCBT.

This run used API-level Django clients against local SQLite; it did not test the deployed cloud, a real school LAN, actual student devices, a live OCBT school license, production PostgreSQL data, payment-provider checkout, or the 10/25/50/100-user OCBT load and outage/restore drills. The existing Phase 6 assessment remains **Not ready for pilot** until those deployment and recovery gates are completed.
