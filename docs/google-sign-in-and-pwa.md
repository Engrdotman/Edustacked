# Google sign-in and EDUstacked PWA

## Google sign-in setup

Google sign-in uses Google Identity Services in the browser. The backend verifies the ID token, its audience, issuer, verified email, and one-time nonce. A Google identity can only link to an existing, active, email-verified EDUstacked account with the same email address. Google sign-in does not register a new school or create a new parent/staff account. Parents and staff must first be invited or provisioned by their school. Platform administrators continue to use the separate platform sign-in route.

1. In Google Cloud Console, create a **Web application OAuth client ID**. Add each exact browser origin under **Authorized JavaScript origins**:
   - `http://localhost:5173` for local Vite development
   - `https://edustackedng.netlify.app` for the Netlify site
   - `https://edustacked.vercel.app` if the Vercel site is still used
   - Add any future custom domain as its own origin.
2. Set `GOOGLE_OAUTH_CLIENT_ID` on the backend (Railway) to that Web client ID. This value is an identifier, not a client secret.
3. Set `VITE_GOOGLE_CLIENT_ID` in the frontend's build environment (Netlify or Vercel) to the **same** client ID, then trigger a new production build. For local frontend development, put it in `frontend/.env.local` and restart Vite.
4. Keep Google client secrets, if any are created for another flow, out of the frontend and out of Git. This implementation uses the browser ID-token flow and does not need a client secret.
5. Apply the account migration before deploying the backend. Deploy the backend and its migration before publishing the frontend button.

Google is offered on school/parent sign-in and platform-admin sign-in only when `VITE_GOOGLE_CLIENT_ID` is set. On first Google sign-in, the backend links the Google subject to the existing matching EDUstacked account. If an account has a different Google identity already linked, support must resolve it; signing in with Google cannot overwrite that link.

## Install and offline behavior

EDUstacked is a responsive web app and can also be installed from the browser as a PWA. There is no downloadable Android APK in this project yet. On desktop Chrome or Edge, use the address-bar install control or browser menu → **Install EDUstacked**. On Android Chrome, use the browser menu → **Install app** or **Add to Home screen**. On iPhone or iPad, open the HTTPS site in Safari, choose **Share**, then **Add to Home Screen**. The same responsive site runs on desktop, tablet, and phone; a PWA install adds an app-style shortcut and window.

The service worker caches only the static app shell, versioned frontend assets, manifest, and app icons. It does not store general API responses, uploaded media, grades, fees, payment details, or parent records. Offline attendance is limited to registers a staff member explicitly prepares on that device while online:

1. Sign in and select the school on the device that will be used for attendance.
2. Open Attendance, create or open a draft register, and choose **Prepare for offline use** while connected.
3. When offline, reopen the app and the prepared register, mark students, and choose **Save draft on this device**. The screen says clearly that these marks are not yet in the school workspace.
4. Reconnect and choose **Sync saved attendance**. The server checks the staff account, school membership, role, teacher assignment, register version, and roster before saving. A version conflict keeps the local copy and does not overwrite the newer school register.

The offline access grant lasts 24 hours. A pending local copy is retained encrypted on that device for up to 30 days, allowing the staff member to reconnect and renew access without losing marks. A register must be prepared separately on each device; offline marks are not shared between devices. Submitting or finalizing a register still requires an internet connection. Device encryption helps protect stored data at rest, but staff should use a device passcode and avoid shared or public devices.

Offline exams continue to use the existing school-local CBT server. That server can run exams already imported and licensed, and later sync its durable outbox to the cloud. Ordinary assessment entry remains online-only.

## Security review notes

See [security-review-2026-11.md](security-review-2026-11.md) for the source-code review scope, current protections, and remaining hardening work.
