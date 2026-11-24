# EDUstacked security review — 22 November 2026

## Scope and limits

This was a source-code review of the Django API, browser authentication, frontend rendering and service worker, payment/SMS callback handling, uploads, and the separate school-local CBT service. It is not a penetration test, an infrastructure review of Railway/Netlify/Vercel settings, or a guarantee that a deployed environment has the right secrets. Dependency advisory lookup could not reach the public npm registry in this environment, so a complete current dependency audit still needs to be run in CI or a network-enabled environment.

## Findings to prioritize

### High: local CBT host can forge cloud-signed exam packages and licenses if compromised

The cloud and school-local CBT service currently share symmetric signing secrets. A person who gains administrator access to a school's local CBT computer could potentially retrieve the shared key and create packages or licenses that the local server accepts. That could be used to alter exam material or bypass local entitlement checks. This requires compromise of that trusted server; it is not a remote unauthenticated exploit found in the reviewed API.

**Mitigation:** migrate to asymmetric signatures: keep the private signing key only in the cloud and distribute a public verification key to school CBT servers. Existing package/license rotation must be planned so current schools are not stranded. Existing project docs already call this out as a future hardening gate.

### Medium: local CBT dashboard traffic needs transport protection on shared networks

The local CBT server is intended for a school's private network. If its operations/admin dashboard is served over plain HTTP across shared Wi-Fi, another person on that network may be able to observe or interfere with unencrypted login/session traffic. This requires network access to the same LAN.

**Mitigation:** do not expose the local service to the public internet; restrict it with the school firewall to trusted devices, use a TLS reverse proxy on shared networks, protect the host account, and keep encrypted off-device backups. The cloud sync endpoint is configured to require HTTPS outside local debug mode.

## Hardening completed in this work

- Replaced an inline JavaScript event handler in the local CBT operations page with a data attribute and delegated event listener. The affected value was already a UUID, but removing the data-to-code path reduces future injection risk.
- Google sign-in is verified on the backend, uses a short-lived single-use nonce, requires Google-verified email and an existing verified EDUstacked account, and does not auto-create users. School, parent, and platform account access remains separated.
- The PWA service worker caches the static application shell only. It explicitly bypasses API, admin, and media paths. Attendance prepared for offline use is stored separately in encrypted IndexedDB, with a register-specific 24-hour sync grant and server-side role, membership, assignment, and version checks. Browser encryption does not protect data from malware or scripts already running in the trusted site origin; staff should use a device passcode and avoid shared devices.
- Service-worker files are configured not to be served from a stale deployment cache, so fixes and removals can take effect promptly.

## Protections confirmed in reviewed code

- Short-lived access tokens are held in frontend memory; refresh tokens use an `HttpOnly` cookie and unsafe auth requests use CSRF protection.
- Password login has request throttling and account lockout controls.
- School-scoped access resolves the user's authorized membership instead of trusting a submitted school ID by itself.
- Payment webhooks validate provider signatures and use idempotent processing; SMS delivery callbacks are signed and duplicate-safe.
- School logo/signature uploads check image content and size using Pillow.
- Production settings require secure cookies/HTTPS behavior and enable HSTS, content-type sniffing protection, and clickjacking protection.

## How an attacker would usually try to use these areas

- A stolen account or school-local computer is the main path to school data. Use unique passwords, keep staff accounts current, revoke access when staff leave, and keep the CBT host physically and administratively protected.
- A school-local host compromise is especially sensitive because of the shared signing-key design described above. Do not give local server administrator access to untrusted users.
- A future frontend mistake that renders untrusted values as HTML or executable JavaScript could let an attacker run code in a user's browser. The inline handler noted above was removed; continue using React's escaped text rendering and avoid `dangerouslySetInnerHTML` for user data.
- A stolen payment webhook secret could let a caller forge callbacks. Keep provider secrets only in the backend secret store and rotate them if exposed; never place them in a `VITE_` variable or commit them.

## Follow-up checklist

1. Move CBT package/license verification to asymmetric signatures before distributing the local server widely.
2. Confirm the local CBT service is not internet-public and that its admin traffic is protected on each school network.
3. Run `npm audit --audit-level=high` and the backend's dependency audit in CI with registry access; review and pin safe updates.
4. Add a Content Security Policy after validating the required Google Identity Services and Pexels image origins; do not apply a restrictive policy blindly because it could break sign-in or the landing page.
5. Review Railway/Netlify/Vercel secret access and rotate any credential previously pasted into chats or support threads.

This review did not find evidence of a universal remote account takeover in the code paths examined. The two findings above need the stated local-host/network prerequisites, and the signing-key design is the main architectural risk to address next.
