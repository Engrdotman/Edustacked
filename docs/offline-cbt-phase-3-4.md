# EDUstacked Offline CBT (Phases 3–4)

This is a separately deployable local Django service for school LAN exams. It uses SQLite only for the local server. The central SMS remains Django + PostgreSQL. Local activity does not require cloud connectivity; the sync worker uploads immutable completed submissions when internet returns.

## Components

- `local_cbt_server/`: independent Django/DRF project and SQLite database.
- `local_cbt_server/student_ui/`: responsive React/Vite student application; questions and answer key remain separated by the local API.
- `backend/apps/cbt/`: central signed package export, per-school local server credentials, submission ingest, and audit dashboard API.

## Central setup and package export

1. Deploy central Django with PostgreSQL as usual. Set a random `CBT_PACKAGE_SIGNING_KEY` secret on central and every trusted local server. Set `CBT_LICENSE_SIGNING_KEY` on both sides to the existing CBT license signing secret. Never place either key in browser code or source control. Changing a signing key invalidates old packages/licenses signed with the old key.
2. Apply central migrations: `python manage.py migrate`.
3. Ensure the school has an active Offline CBT entitlement, publish an examination, assign eligible enrolled students, and configure enough license capacity.
4. A school administrator with `cbt.exams.publish` POSTs `/api/v1/cbt/examinations/{exam_id}/package/`. The response includes `signed_payload`; save it as a JSON file on a trusted admin computer and transfer it to the LAN server. The current version creates one immutable package per exam; changed exams require a future explicit version/export workflow.
5. Create a local-server bearer credential from `POST /api/v1/cbt/local-servers/` (the plaintext is returned once), and store it only in the local server environment. Local server management endpoints are listed under `/api/v1/cbt/local-servers/` and sync status at `/api/v1/cbt/sync/dashboard/`.

The signed package contains snapshots, assignment mapping, instructions, dates, and an answer key. Local import validates the signature/checksum, package schedule, assignment map, license signature and license grace. The answer key is stored in a separate local database field and is never present in student API responses. The package signing mechanism uses Django's timestamped signing with a shared secret. Restrict the key to central and the trusted local server; the local administrator host therefore remains part of the signing trust boundary. See [Phase 6 security/readiness](offline-cbt-phase-6-production-readiness.md) for the risk and controlled key-rotation guidance.

## Local server installation (Windows, Linux, or macOS)

Use a supported Python 3.11+ environment and Node.js 20+ on the trusted server. SQLite requires no separate database service. From this folder:

```powershell
cd local_cbt_server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` before starting. Use a generated secret for `LOCAL_CBT_SECRET_KEY`, `CBT_PACKAGE_SIGNING_KEY`, `CBT_LICENSE_SIGNING_KEY`, `CENTRAL_SYNC_TOKEN`, the central API URL, and `LOCAL_CBT_ALLOWED_HOSTS` (server hostname/IP). `CENTRAL_SYNC_TOKEN` must be the one-time central bearer credential. `LOCAL_CBT_DATABASE` may point to a persistent volume; its parent is created automatically. Keep server and student devices on the same trusted LAN/VLAN and allow inbound TCP to the configured port in the host firewall. Do not expose Django's development server to the public internet.

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8001
```

For a school deployment, run Django through a production WSGI server such as Waitress on Windows or Gunicorn on Linux/macOS behind the school's HTTPS-capable reverse proxy. Bind to the LAN interface only. Keep the local SQLite file and backups on persistent encrypted storage; avoid concurrent copies of the live database.

## Student interface and package import

In a second terminal:

```powershell
cd local_cbt_server/student_ui
npm install
npm run dev
```

Open the Vite URL shown in the terminal from student computers on the LAN. Vite proxies `/local/api` to `127.0.0.1:8001`. For production, build with `npm run build` and serve the generated `dist` directory from a static web server/reverse proxy on the same LAN hostname; proxy `/local/api/` and `/admin/` to the Django service. The React app uses relative API paths and needs no cloud or third-party assets.

Sign in to `/admin/` with the local Django superuser. Use the **Package imports** API `POST /local/api/v1/admin/packages/import/` with JSON `{ "signed_payload": "..." }`, or use the shell helper below to import a file without putting large package data in the URL:

```powershell
$env:LOCAL_CBT_SECRET_KEY = 'your-local-secret'
python manage.py shell -c "import json; from offline_exam.services import import_package; p=json.load(open('package.json', encoding='utf-8'))['signed_payload']; print(import_package(p)[0])"
```

Create local student credentials from the central student ID and admission number already present in the signed assignment map. This is a local exam-only password, independent of central login:

```powershell
python manage.py create_local_student --central-student-id 123 --admission-number ST-001 --name 'Student Name'
```

The command prompts for a 12+ character temporary password. Deliver it privately through the school. Do not send it in a public class group. Local student credentials are password-hashed and lock after repeated failures.

## Exam integrity and recovery

The server validates schedule, assignments, maximum attempts, active-session uniqueness, answer shape, and expiry. Its server clock decides when the session expires; the browser countdown is only a display. Each answer is written to SQLite with a UUID request key. Refresh reloads authoritative server answers. If the LAN connection drops, the browser temporarily queues the last unsaved answer in session storage and retries it with the same idempotency key; this temporary queue is not a backup and students should remain connected whenever possible. Submitted sessions and submission snapshots cannot be edited or reopened. Timeout is finalized on the next student/server request, including recovery after a server restart.

## Sync, monitoring and recovery

Start the durable outbox worker in a separate process (configure it as a Windows service/systemd unit in deployment):

```powershell
python manage.py sync_outbox --loop --interval 30
```

It sends completed raw submissions only; transient navigation and each answer change are not synchronized. HMAC signatures bind the canonical JSON payload to the per-school bearer secret. Central checks the server identity, signed package ownership, assignment/student match, payload version, exam question IDs and answer format, entitlement/grace policy, event UUID, and local-session id. Repeated identical deliveries return accepted/duplicate; altered event/session replays are audited as conflicts. Failures use exponential backoff and become manually retryable after the configured retry limit. Central now calculates CBT results after accepted sync; see [Phase 5 Results and Analytics](offline-cbt-phase-5-results.md). CBT scores still do not alter school report cards.

At `/operations/`, authenticated local Django staff can view imported packages, sessions, outbox/retry status, import signed packages and renewed signed licenses, run sync/retry actions, download the original signed package, and create an integrity-checked database backup. `/admin/` exposes the detailed model lists. Admin API endpoints: `GET /local/api/v1/admin/overview/`, `GET/POST /local/api/v1/admin/sync/` (`sync_now`, or retry by event ID), `POST /local/api/v1/admin/licenses/import/`, `GET /local/api/v1/admin/packages/{package_id}/backup/`, and `GET /local/api/v1/admin/backup/`. Backups use SQLite's online backup API plus `PRAGMA integrity_check`; schedule encrypted off-server copies, apply a retention policy, and rehearse restore with the service stopped.

## Capacity and operations

The code has not been load-tested with 100 concurrent students. Use a wired gigabit LAN where possible, a server with SSD, 4+ CPU cores and 8 GB RAM as an initial pilot baseline, and test realistic concurrent login, question fetch, autosave and submit traffic before a live school exam. Capacity depends on question images, host hardware, browser devices, and backup/sync activity. Do a supervised pilot and retain a paper/alternate-exam contingency. Synchronization never blocks local exam work.

## Known limitations

- Report-card generation from CBT scores is not included; CBT results are managed in the separate Phase 5 results workflow.
- Signed license dates/grace are checked at package import and each new exam start. A running exam is allowed to finish. While offline, the server cannot learn about immediate cloud revocation; an administrator can import a renewed signed license through `/operations/`.
- Central ingest retains immutable raw answer snapshots and creates a separately audited central result; scoring details are documented in the Phase 5 guide.
- Package export currently creates one immutable version per exam; replace/reissue workflow and revocation for already imported offline packages need an explicit admin process.
- The local app's admin workflow is Django Admin/API rather than a custom branded dashboard.
- Local student-account provisioning/reset is an administrator CLI process; account delivery is a school responsibility.
- No performance test has established the 100-student target.
