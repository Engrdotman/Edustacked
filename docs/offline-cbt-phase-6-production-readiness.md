# Offline CBT Phase 6: Security, Operations, and Readiness

This guide records the Phase 6 audit, hardening changes, verified behavior, and outstanding operational gates. Read it with [Phases 0–1](offline-cbt-phase-0-1.md), [Phase 2](offline-cbt-phase-2.md), [Phases 3–4](offline-cbt-phase-3-4.md), and [Phase 5](offline-cbt-phase-5-results.md).

## Architecture and trust boundaries

- **Central cloud SMS:** React + Django REST Framework + PostgreSQL in production. It owns school memberships/RBAC, CBT service plans and entitlements, question banks, published exam snapshots, assignments, package signing, sync credentials, result processing, analytics, and mark audit history.
- **School-local CBT server:** separate Django application and SQLite database. It verifies signed exam packages and licenses, authenticates local student accounts, owns exam timing, sessions, saved answers, submissions, and the durable sync outbox. It does not need central internet access for an exam already imported and licensed for offline use.
- **Student browser:** React application served from the school LAN. It receives question text/options and the student's saved response, never the answer key. The browser timer is only a display; the local server's timestamps govern session expiry.
- **Synchronization:** signed/HMAC-authenticated local submissions are retried with their immutable event and session IDs. Central processing is idempotent and creates results from the published snapshots; text answers wait for authorized marking.

The local server is a trusted school system. Current Django package/license signing uses a symmetric key shared with the central service. A local host administrator who obtains that key could forge packages/licenses. Protect and rotate these secrets through a controlled maintenance plan. Move to central-private-key/local-public-key signing before broad distribution; Phase 6 does not claim the shared-key design is safe against a compromised school host.

## Security controls and remaining limits

- Central CBT APIs require authenticated school context, school-role permission, and an active separate CBT entitlement. Teachers' result access is limited to active teaching assignments. CBT entitlement does not gate core school-management features or report-card credits.
- Local student passwords use Django password hashing; student tokens are random, stored as hashes, revocable, and expire within a configured 1–24 hours. Login is rate limited and lockout applies after repeated failures. Unknown accounts use a dummy password hash check to reduce timing-based account discovery.
- Local session, answer, and submit endpoints bind session IDs to the authenticated student. The LAN server pins imported packages/licenses to one school. Admin endpoints require a Django staff/superuser session and Django CSRF protection.
- Package/license signatures are verified with Django's maintained signing implementation. Signed exam data and answer keys are stored separately in the local database; the signed original package is retained for backup by authorized administrators.
- Answer values are validated against package snapshots on local save and again against central examination snapshots on ingest. Client-supplied scores are not accepted. The server's clock determines the session deadline; attempts to save after expiry auto-submit the server-saved answers and are rejected.
- Answer writes and submission share a database transaction and row lock. A browser queues the latest unsaved answer temporarily in `sessionStorage` and retries it with an idempotency UUID. Serialized client writes prevent fast text typing from being saved out of order.
- The browser queue is temporary. It can be lost if the tab/browser/device closes or power fails before the LAN server acknowledges the answer. Only answers acknowledged by the local server are guaranteed to survive browser refresh or process restart, assuming persistent healthy storage. Do not claim unsaved browser answers are recoverable.
- Local API calls are designed to be same-origin; do not enable wildcard CORS. Use HTTPS for the local admin/student origin in production and configure a reverse proxy to strip inbound spoofed forwarding headers. If the proxy is counted, set `LOCAL_CBT_NUM_PROXIES` to its exact trusted count. Keep `CENTRAL_SYNC_VERIFY_TLS=true`; production settings reject an HTTP sync URL or disabled certificate verification.

## Windows school-server setup

Use a dedicated school-owned Windows computer/server with persistent storage. The local service has been designed for Windows commands, but installation and production operation still need a supervised site rehearsal.

1. Install supported Python 3.11+ and Node.js 20+. Create a dedicated, non-administrator Windows service account with write access only to the CBT data and logs directories.
2. In PowerShell:

   ```powershell
   cd C:\EDUstacked\local_cbt_server
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Edit `.env`. Generate a random `LOCAL_CBT_SECRET_KEY` of at least 32 characters. Provision the package/license verification keys and one-time `CENTRAL_SYNC_TOKEN` through a secret manager or protected admin procedure. Set `LOCAL_CBT_ALLOWED_HOSTS` to the exact local host names/IPs. Keep `CENTRAL_SYNC_VERIFY_TLS=true`. Do not put secrets in the student UI, Git, screenshots, or shared class materials.
4. Initialize database and administrator:

   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   .\.venv\Scripts\python.exe manage.py createsuperuser
   .\.venv\Scripts\python.exe manage.py collectstatic --noinput
   ```

5. Build the student UI and serve it from the same HTTPS LAN origin as the API:

   ```powershell
   cd student_ui
   npm ci
   npm run build
   ```

   Host `student_ui\dist` as static content behind an HTTPS-capable reverse proxy. Proxy `/local/api/`, `/admin/`, and `/operations/` to Django. Terminate TLS at the proxy, use a certificate trusted by student devices, and do not expose Django's development server to the school Wi-Fi or public internet.

6. Run the Django app on loopback behind that proxy:

   ```powershell
   cd ..
   .\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8001 localcbt.wsgi:application
   ```

   Run `python manage.py sync_outbox --loop --interval 30` as a second service/process. Configure both processes to start on boot and restart on failure using the school's approved Windows service manager. Keep static UI, API, and admin paths same-origin. Allow inbound firewall traffic only to the HTTPS proxy port from the school LAN/VLAN; keep port 8001 private to loopback. The sync worker is not required while internet is unavailable.

7. Open `/operations/` from an administrator device. Sign in with the local Django staff account. Create local student logins using `python manage.py create_local_student --central-student-id <ID> --admission-number <NUMBER> --name <NAME>`; the command prompts for a password. Deliver each student their local exam password privately.

For a non-production lab only, Django `runserver 0.0.0.0:8001` and the Vite development UI can help verify one exam. They do not provide production TLS, service supervision, or performance evidence.

## Central production deployment

- Keep central PostgreSQL enabled; production configuration rejects SQLite. Configure `DATABASE_URL`/PostgreSQL connection variables, backups, connection limits, TLS, and restricted network access using the existing SMS deployment process.
- Set production `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, HTTPS CORS/CSRF origins, HTTPS proxy settings, and secure cookies as documented in the central deployment environment. Never use wildcard origins or `DEBUG=true` in production.
- Set stable, random `CBT_PACKAGE_SIGNING_KEY` and `CBT_LICENSE_SIGNING_KEY` values in the secret manager. The current local verifier requires matching keys; changing either invalidates corresponding existing signed objects unless a coordinated reissue/rotation is performed. `CBT_OFFLINE_GRACE_DAYS` is centrally limited to 0–90 days and is embedded in signed license records.
- Apply migrations in the deployment pipeline with `python manage.py migrate`; run `python manage.py check --deploy`. Configure static/media storage, HTTPS, error monitoring, central logs, database backups, and alerting as for the rest of the SMS.
- Do not copy central sync bearer tokens or signing keys into public React assets. Local sync credentials are per-school, shown once, and should be rotated if lost.

## Exam preparation and operation

Before exam day, activate the separate Offline CBT entitlement, confirm capacity, create/publish questions and an exam, assign active students, and export the signed package. Transfer the package to an administrator computer and import it at `/operations/`. The package contains the immutable student assignment map and answer key, but student endpoints never return that key. Create local student accounts and distribute credentials privately.

On exam day, verify the school's local license, date/time/timezone, network, storage space, backup, exam schedule, student devices, and power plan. Students open the LAN HTTPS URL, sign in with the local account, start/resume their exam, and keep the browser open and connected. Answers are saved per change to the local server; the page indicates when a save remains pending in the browser. The server finalizes timed-out sessions on the next request or outbox-worker pass after the deadline. A power interruption can still lose an answer that had not yet reached the server.

If a student refreshes, server-acknowledged answers reload from the local server. After a browser or device restart, the student can sign in again and resume the server's existing active session. If the LAN drops, the UI retries queued values when it reconnects; do not close the tab while a save is pending. If the local server restarts, committed SQLite answers/outbox entries remain on persistent storage; the sync worker recovers expired sessions and retries the outbox when restarted. Keep a paper/alternate exam procedure for server, network, power, or device failure.

## Synchronization and central results

Use `/operations/` or Django Admin to inspect pending/failed outbox events. A failed event can be manually requeued; retry uses the same immutable event ID. The local row becomes `synced` only after central returns an accepted/duplicate response. If a request is interrupted after central accepted it, the next attempt is deduplicated centrally and can then be marked synced locally. A conflicting replay is retained for administrator review and never silently overwrites the central submission/result.

When the internet returns, the outbox worker posts submissions. Staff review central CBT results at `/app/cbt/results`, correct essay marks with a reason, and export CSV. CBT scores do not currently populate school report cards. A local school cannot see the state of an unsent submission from the central dashboard until it reaches central.

## License renewal while offline

1. A platform administrator activates/renews the school's `offline_cbt` entitlement centrally.
2. A school user with service access opens `/app/services`, downloads the signed license JSON, and transfers it to the authorized local server administrator through a protected channel.
3. In `/operations/`, import the JSON in **License renewal**. The local server verifies its signature, school ID, service code, dates, and grace, then displays the license state. Already imported exams can start under the current signed entitlement while within its offline-valid period.
4. When a server is offline, immediate cloud revocation is impossible. The server relies on signed start/expiry dates and the configured grace period. An imported exam cannot start before license start or after the expiry+grace boundary. Import an updated signed license to renew offline access. Core SMS workflows remain available regardless of CBT status.

## Backups and restore

- From `/operations/`, choose **Download SQLite backup**. The endpoint uses SQLite's online backup API to snapshot an active database, runs `PRAGMA integrity_check`, and records the last generated/verified backup time and size. Active exams are not stopped by the snapshot.
- The database backup contains students, sessions, acknowledged answers, outbox state, imported exam snapshots, answer keys, and the original signed package. Administrators can also download each original signed package from the package list. Store the database backup and any separately transferred signed license JSON encrypted and off the server; verify the downloaded backup independently before relying on it.
- Recommended retention: keep daily encrypted backups for 14 days, weekly copies for 8 weeks, and monthly copies for 12 months, subject to school policy and storage capacity. Retain at least one copy offline/off-site. The application creates and verifies a snapshot on request; Windows service scheduling, encrypted off-host transfer, and retention pruning must be configured by the school IT operator.
- To restore, schedule downtime, stop the Django and sync-worker services, preserve the current database file, copy the chosen backup to the configured `LOCAL_CBT_DATABASE` path, and verify with `sqlite3 backup.sqlite3 "PRAGMA integrity_check;"` or an equivalent SQLite client. It must return `ok`. Restart the server and worker, check `/operations/`, confirm packages/sessions/outbox counts, and test one student account before resuming exams. Do not replace a live database file while Django or the worker is running.
- A restored outbox can safely retry events already accepted centrally: central idempotency returns duplicate/accepted for the same event hash. Keep the backup's sync event IDs and payloads intact; never edit a failed event payload to make it pass.

## Reliability, performance, and manual pilot checklist

Local automated tests cover signed package validation and duplicate import, student authentication and ownership isolation, answer validation/save/refresh, idempotent submission, server-side expiry, simultaneous active sessions for two students, sync outage/retry, license expiry/renewal, package school isolation, and integrity-checked database backup. The central suite covers school tenant/RBAC boundaries and signed/idempotent ingest-to-result processing.

A Locust scenario is provided in `local_cbt_server/loadtests/locustfile.py`. It requires a private CSV of unique assigned accounts and an active published exam. Run against a test server, not during a live exam. For each scenario, prepare 10, 25, 50, then 100 unique test students and run:

```powershell
cd local_cbt_server
pip install -r loadtests\requirements.txt
$env:LOCAL_CBT_STUDENT_CREDENTIALS = 'C:\secure\cbt-load-users.csv'
locust -f loadtests\locustfile.py --headless --host https://cbt-test.school.lan --users 10 --spawn-rate 2 --run-time 5m --csv results-10
```

Repeat with `--users 25 --spawn-rate 5`, `--users 50 --spawn-rate 10`, and `--users 100 --spawn-rate 20`, updating the output prefix each time. Record p50/p95/p99 and failures for login, list/start, question/session read, answer saves, and submission from Locust's CSV/summary. Simultaneously record Windows CPU, available memory, and disk latency with Performance Monitor; record server model, CPU/RAM/SSD, Windows version, LAN switch/Wi-Fi, and client-device mix. The default login throttle is 20/minute per source IP; a single Locust injector shares one IP. Test with realistic client IPs or a protected test-only throttle/proxy arrangement; do not weaken live login controls. Run interruption tests separately from load runs.

Manual checks still required before pilot: disable WAN before and during an exam; disconnect/reconnect a student LAN link; refresh and restart a browser; restart Django and the sync worker; safely test a host restart/power recovery with disposable data; submit duplicate save/submit requests; try a save after expiry; interrupt a sync request after central acceptance; restore a verified backup to a separate database; and observe concurrent submissions. Do not simulate a real power cut on a school production database.

## Pre-exam operational checklist

- [ ] School and exam dates/timezone verified against local server time.
- [ ] Active signed CBT license and student capacity checked; core SMS remains independent.
- [ ] Correct exam package imported; package and license backups stored off-server.
- [ ] Eligible students assigned; local login accounts/password delivery verified.
- [ ] Student devices and LAN tested; local HTTPS certificate trusted; firewall permits only intended LAN path.
- [ ] Persistent disk space, UPS/power plan, and latest integrity-verified backup confirmed.
- [ ] Django service and outbox worker start/restart successfully; admin can open `/operations/`.
- [ ] Paper/alternate exam procedure and administrator contact are available.
- [ ] Staff know that browser-pending answers are not server-saved until acknowledged.
- [ ] After exam, confirm completed local sessions, pending/failed sync, central result count, duplicate/conflict state, and backup.

## Readiness outcome

**Not ready for pilot based on evidence currently available.** Security and application-level fixes have been added and automated checks are recorded in the audit report, but there is no measured 10/25/50/100-student run, school hardware/network record, production HTTPS rehearsal, destructive-recovery rehearsal, or physical outage/power recovery evidence. The shared symmetric signing secret on the local server is also a high-risk trust limitation. Complete those gates with a supervised test school before a controlled pilot; do not claim broad deployment support.
