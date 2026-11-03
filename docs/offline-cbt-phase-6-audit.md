# Offline CBT Phase 6 audit and readiness record

Audit date: 2026-11-03. Scope: central Django API/entitlements/results, local Django/SQLite service, student React client, package import and synchronization, backups, documentation, and automated tests. The repository state was inspected before the Phase 6 hardening edits.

## Architecture reviewed

- Central cloud service: the existing multi-tenant Django REST application; CBT/entitlements are separately installed modules and the central production database is configured for PostgreSQL.
- School server: separate Django application using SQLite and a durable database-backed answer store and sync outbox.
- Student client: same-origin React UI using a short-lived local bearer token and session storage.
- Sync: one immutable submission event per local session; retries use the same event ID; central ingest checks its signature, school credential, package, student assignment, payload hash, and event/session duplicates.
- Results: accepted central submissions create immutable result snapshots; essay marks/corrections append an audit entry.

## Findings before Phase 6 edits

| Area | Finding | Risk / status |
| --- | --- | --- |
| Tenant isolation and RBAC | Central CBT endpoints resolve an authorized school, apply role permissions and entitlement checks, and scope data. Result views further filter teachers by active teaching assignment. Local student session endpoints query by both session ID and authenticated student. | Existing tests cover central cross-school/role denial and local session ownership; continue regression coverage. |
| License independence | CBT endpoints require a current Offline CBT entitlement. The core SMS does not depend on the entitlement app's CBT gate. Local license data is signed and imported with the exam package. | Verify the local license again when starting an already imported exam; an import-time check alone can leave an expired package startable later. Addressed in Phase 6 edits. |
| Signing-key trust | Central package and license signatures use Django's maintained timestamped signing, but the symmetric signing secret is copied to the local server. A compromised local host can mint packages/licenses. | High risk before broad rollout. Use isolated key custody; a future asymmetric-signature migration is recommended before broad distribution. No custom cryptography introduced. |
| Authentication | Local student passwords use Django password hashers; student bearer tokens are random, stored hashed, revocable, and expire. Login is throttled and lockout applies after repeated failures. Django admin uses framework authentication. | Controls are present. Tokens are held in `sessionStorage` and expire after the configured period; require re-login after browser restart/session expiry. |
| Exam answer protection | Imported answer keys are stored separately from student-facing exam config. Student responses expose only their own saved answer. Central result details withhold correctness/explanations until exam end. | Maintain this boundary with tests. |
| Server timing and session recovery | The server sets session expiry and auto-submits on the next request or sync-worker pass. Refresh reloads server-saved answers; browser clock only renders countdown. | Unsaved client text can be lost on device/browser failure. Browser retry can issue overlapping writes; answer-write versus submit needs a transaction/lock boundary. Addressed in Phase 6 edits and tests. |
| Offline reliability | Local server does not need internet to authenticate, start, save, or submit. Browser temporarily queues unsaved answers in `sessionStorage`; committed server answers survive browser refresh and server process restart if SQLite storage persists. | No simulated power-cut or physical LAN test has been run. Browser-local unsaved answers are not guaranteed after tab/browser/device loss. |
| Sync | Durable outbox, retry backoff, terminal failure/manual retry, event IDs, central idempotency, and an admin queue view are implemented. The outbox is marked synced only after a 2xx response with `accepted: true`. | Existing tests cover a temporary outage then acceptance and timeout submission. No interrupted-process, multi-worker, or physical internet-disconnect test has been run. |
| Backups | An authenticated admin endpoint uses SQLite online backup, which is intended to snapshot a live database safely. | The response was not integrity-checked, no last-success indicator or retention scheduler existed, and uploaded signed source package files were not retained in the database. Address backup verification/status; off-host retention and restore drills remain operational requirements. |
| Local operations UI | `/operations/` shows local license, active sessions, package list, pending/failed sync, and allows import/retry/backup. | Connected browsers are not reliably observable and must not be represented as connected-student counts. Health and last backup visibility are incomplete; improve those indicators. |
| CORS/CSRF/transport | Student UI is intended to be served same-origin; Django CSRF middleware and session-auth CSRF apply to admin APIs; bearer student APIs use token auth. TLS verification is on for sync by default and can be disabled by configuration. | Production must keep TLS verification enabled, use HTTPS for admin/session access, restrict hosts/firewall, and avoid publicly exposing `runserver`. |
| Input/error handling | Django ORM prevents SQL string interpolation in the examined paths. Login/answer inputs are validated and generic login failure messages are returned. | Malformed signed nested package structures could raise uncaught type errors; convert these to actionable validation failures and cover malformed packages. |
| Performance | Existing tests exercise two simultaneous active students only. | No 10/25/50/100-user measurements exist. The 100 concurrent student target is unverified; do not treat as supported. |

## Phase 6 work completed

- Added server-side license checks on every new exam start, an authenticated local admin import for renewed signed licenses, and authorized central license download. Renewal applies to the same pinned local school; the running exam is not interrupted.
- Pinned a local CBT server to one school ID, including license updates, so a second school's packages cannot be imported into that server.
- Made answer persistence and finalization share a transaction/row-lock boundary, serialized browser answer saves, debounced essay typing, displayed pending saves accurately, and blocked manual submit until queued answers are acknowledged.
- Reduced login account-enumeration timing and capped login input lengths; bounded token lifetime and configuration; production local sync requires HTTPS and certificate verification.
- Added package structural validation, retained original signed package files in the local database, and exposed download only to local administrators.
- Added an integrity check and backup audit record to the online SQLite backup path, surfaced last verified backup in operations, and added a school operations/load-test guide.
- Added regression tests for expired-license refusal and renewal, school pinning, post-expiry answer rejection/auto-submit, other-student session denial, malformed signed package input, admin-only package backup, and verified database backup.

## Verification and acceptance

- Local service: `manage.py check` passed; `makemigrations --check --dry-run` reported no model changes; `manage.py test offline_exam` passed all 16 tests (2026-11-03).
- Central service: `manage.py check` passed; `makemigrations --check --dry-run` reported no model changes; `manage.py test apps.cbt apps.entitlements` passed all 22 tests (2026-11-03). This includes the dedicated signed-license endpoint's school-admin authorization test.
- Frontend React modules and local student UI passed syntax parsing. `git diff --check` passed. A full Vite production build was not verified in this environment because the earlier build was blocked by sandbox access in esbuild; the local student UI dependencies are also not installed.
- No Locust load run, production HTTPS rehearsal, real school LAN/WAN interruption, server/power restart, hardware telemetry collection, or supervised restore drill was performed. These require a configured test school/server and must be completed before pilot.

The implementation and automated tests improve application-level security and recovery behavior, but the evidence is insufficient for pilot acceptance. The shared symmetric signing secret on a local server remains a high-risk trust limitation. Acceptance outcome: **Not ready for pilot** until the load, deployment, recovery, and key-custody gates in the production-readiness guide are completed.
