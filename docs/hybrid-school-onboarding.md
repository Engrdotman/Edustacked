# Hybrid school onboarding

EDUstacked allows a school representative to create a school workspace and begin setup independently. Platform review provides a separate trust decision; it does not block ordinary setup.

## Registration flow

```text
Public website
  -> Register school (administrator + school details)
  -> Atomic creation: school + account + owner membership + settings + onboarding progress
  -> Email verification link (expiring, single-use token)
  -> Verified account signs in and opens the school onboarding wizard
  -> School can configure profile, academic year, structure, and staff while pending
  -> Platform administrator reviews school evidence
  -> Verified | Rejected (reason) | Suspended (reason)
```

## Account verification and school verification

These represent different things. `User.email_verified_at` and `phone_verified_at` record the account holder's contact verification. Signup sends a random email token; only its SHA-256 digest is stored, and the selector/token pair is single-use and expires according to `EMAIL_VERIFICATION_TIMEOUT`. Phone verification fields are ready for a future OTP provider; no SMS is sent currently. `School.verification_status` represents platform review (`pending_verification`, `under_review`, `verified`, `rejected`, `suspended`). A verified contact address is not evidence that a school is legitimate.

New schools can access normal school setup while pending. Capabilities that require platform verification are centrally configurable through `SCHOOL_VERIFIED_REQUIRED_CAPABILITIES` (defaults to `integrations.manage`) and checked by `HasSchoolPermission`. Rejected schools retain their records and receive the review reason. Suspended schools are excluded from ordinary tenant resolution; platform superusers retain review access.

## Ownership, membership, and tenant isolation

The first registrant receives a `school_owner` membership. Owner and principal permissions are enforced by backend permission classes, in addition to frontend route visibility. Owner membership cannot be changed through ordinary membership editing. Transfer requires the current owner's password, a verified account already belonging to the same school, and an atomic update; the transfer is audited. Platform administration requires Django `is_superuser` and is a separate API/UI area.

School APIs resolve the tenant from the authenticated membership plus `X-School-ID`; a client-provided school ID alone never authorizes access. Suspended schools fail tenant resolution, and object/query access remains scoped to the resolved school. Platform review changes create immutable `SchoolVerificationEvent` audit records with actor, school, status transition, reason, and timestamp.

## Onboarding progress

`SchoolOnboardingProgress` persists the current wizard step. Completion is calculated from existing school profile, academic session/term, class/subject, and staff data, so users can leave and resume. The wizard is guidance; optional steps do not prevent dashboard access. The progress endpoint is `GET/PATCH /api/v1/schools/onboarding/`.

## API endpoints

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `POST /api/v1/auth/signup/` | Public, throttled | Register account and school; sends email verification |
| `POST /api/v1/auth/verify-email/` | Public, throttled | Consume expiring single-use token and establish session |
| `POST /api/v1/auth/verify-email/resend/` | Public, throttled | Resend verification without account enumeration |
| `POST /api/v1/auth/demo-request/` | Public, throttled | Submit demo request |
| `GET/PATCH /api/v1/schools/onboarding/` | School owner/admin/manager/principal | Read summary and save wizard step |
| `POST /api/v1/schools/<school_id>/ownership/transfer/` | Current school owner | Transfer ownership with password confirmation |
| `GET /api/v1/schools/platform/schools/` | Platform superuser | Search/filter school registry |
| `GET /api/v1/schools/platform/schools/<id>/` | Platform superuser | View school and audit details |
| `POST /api/v1/schools/platform/schools/<id>/{review,verify,reject,suspend,reactivate}/` | Platform superuser | Review lifecycle actions; rejection/suspension/reactivation require a reason |

## Platform administrator responsibilities

Platform administrators review registrations, record a reason when rejecting/suspending/reactivating, verify appropriate schools, and respond to demo requests through the existing database/admin workflow. School administrators cannot access the platform registry. Audit events are available on school detail and Django admin.

## Local setup and testing

Use SQLite for local development. Configure `FRONTEND_BASE_URL=http://localhost:5173`; development email uses Django's console backend unless overridden, so the verification URL is printed in the backend terminal. Configure SMTP with `EMAIL_*` settings to deliver actual email. PostgreSQL remains the production database option.

```powershell
cd backend
python manage.py migrate
python manage.py check
python manage.py test apps.accounts apps.schools
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Register at `/signup`, follow the verification URL, then continue at `/app/onboarding`. Create a Django superuser with `python manage.py createsuperuser` to use `/platform/schools` for review. The backend tests cover registration, duplicate prevention, email token expiry/reuse, owner creation/transfer, onboarding progress, pending/verified capability gates, platform permissions, lifecycle restrictions, audit history, and tenant access.
