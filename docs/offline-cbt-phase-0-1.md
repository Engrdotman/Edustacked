# Offline CBT architecture audit and Phase 1 boundary

## Phase 0 audit

The repository is an existing React/Vite frontend and Django 5.2 / Django REST Framework modular monolith. The API is versioned under `/api/v1/`. The custom `accounts.User` authenticates with JWT; school roles live in `SchoolMembership`, and `HasSchoolPermission` plus `resolve_authorized_school` enforce membership-based school context. Tenant models use explicit foreign keys to `School` and the shared database schema.

Central development defaults to SQLite. Production rejects SQLite when `DEBUG` is false and supports PostgreSQL through `DATABASE_URL` or `DB_ENGINE=postgresql`. The existing billing app is specifically a Paystack-backed report-card credit ledger: it charges one credit per finalized student report card/term. It has no subscription, service catalog, school service-entitlement, or CBT models. Reusing its credit balance or ledger for CBT would break the documented charging rule, so add-on services need separate records and payment fulfillment.

Completed reusable modules include schools/memberships and RBAC, academics (sessions/classes/subjects/grading), students/enrollments, staff assignments, attendance, assessments/results, report cards, report-card credit billing, parent portal, and reports. No CBT application, question/exam models, local CBT server, package transfer, or sync engine exists yet.

## Integration points and risks

- Keep the cloud CBT administration inside this modular monolith and reuse JWT, school membership and school-scoped query patterns.
- Put reusable catalog and entitlement records in a separate `entitlements` Django app. Keep report-card credits and their Paystack callbacks independent.
- Gate every future CBT API with both its normal school-role permission and an `HasActiveServiceEntitlement` check; tenant filtering remains mandatory even when licensed.
- The local examination server is a future independently deployable Django/React component, initially SQLite. It must own offline sessions and answers; the cloud is not a runtime dependency during exams.
- Phase 1 issues a signed HMAC license payload for offline verification. Local deployment must receive the matching verification secret under secure provisioning; moving to an asymmetric public-key verifier before broad local distribution would avoid copying the cloud signing secret and is a Phase 3 production gate.
- No CBT prices, package tiers, renewal policy, or payment UX were specified. Phase 1 stores configurable separately-priced plans and allows audited platform activation after payment confirmation; it does not invent prices, simulate checkout, or redirect the report-card credit flow.
- An offline server cannot learn immediately about cloud-side revocation without internet. It applies the license expiry and configured grace window locally; renewal/revocation reconciliation belongs to the later sync phase.

## Phase 1 implemented

- `ServicePlan` is a generic, separately-priced service catalog entry with service code, plan key, student capacity, duration, amount, currency and active state.
- `ServiceEntitlement` is a school-scoped, auditable grant with its own plan, dates, capacity, payment reference, status, unique license identifier, and signed offline license payload. Historical licenses remain available for renewal/audit.
- Schools with active membership can read only their own service plans and license records. Platform superadmins can issue a grant through a protected API or Django Admin. School administrators and accountants can see service state; principal can see it as well.
- `HasActiveServiceEntitlement` provides the entitlement check for future service endpoints. Phase 2 CBT APIs must combine it with role permissions and school-scoped querysets.
- The frontend dashboard links eligible school roles to an optional-services page that shows the actual license status and configured plans. It makes clear that checkout is not yet implemented.

## Phase 1 API

All school requests authenticate with the existing JWT and pass `X-School-ID` as context. Membership resolution is still server-side.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /api/v1/services/plans/` | School role with `services.view` | Active separately-priced service catalog |
| `GET /api/v1/services/entitlements/` | School role with `services.view` | The selected school's current and historical grants |
| `GET, POST /api/v1/platform/services/entitlements/` | Django superuser | Audit/query grants and activate a grant after payment confirmation |

Platform grant requests include `school`, `service_code`, `package_type`, `student_capacity`, `starts_on`, `expires_on`, optional `plan`, and optional unique `payment_reference`. The signed token is generated server-side and cannot be supplied by the client.

## Migration and local setup

After applying migrations, create service plans in Django Admin or application code. Configure `CBT_LICENSE_SIGNING_KEY` to a random secret in the central deployment and securely provision the matching verifier key to the future local CBT server. `CBT_OFFLINE_GRACE_DAYS` defaults to 7. Never commit either secret. No default price is seeded because plan pricing was not specified.

Phase 1 does not include checkout/renewal payment UX, question banks, exams, student examination sessions, local deployment, packages, synchronization, objective marking, or analytics. Those are later phases; Phase 2 is question bank and exam management.
