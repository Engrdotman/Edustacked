# Railway Deployment Checklist

This checklist ensures proper configuration for Railway deployments and prevents migration conflicts.

## Pre-Deployment Verification

- [ ] GitHub main branch has been reviewed and all features are approved
- [ ] All GitHub Actions tests pass (check workflow runs on main)
- [ ] DJANGO_SECRET_KEY is unique and never reused from local/test environments
- [ ] PostgreSQL service is created in Railway (and remains **private**, no public database URL)
- [ ] Backend service Root Directory is set to `/backend`

## Backend Service Configuration

### Build and Start Commands
- [ ] Build Command: `python -m pip install --upgrade pip && python -m pip install -r requirements.txt`
- [ ] Pre-Deploy Command: `python manage.py migrate --noinput`
- [ ] Start Command: `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

**Critical:** Do NOT include migrations in the Start Command. Migrations run in Pre-Deploy only.

### Health Check
- [ ] Healthcheck Path: `/api/v1/health/database/`
- [ ] Restart policy: On failure

### Environment Variables
Required production variables (set in Railway backend service Variables):

| Variable | Example Value |
|---|---|
| `DJANGO_SECRET_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference your PostgreSQL service) |
| `DJANGO_ALLOWED_HOSTS` | `edustacked-api-production.up.railway.app,api.yourdomain.com` |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `https://your-vercel-project.vercel.app,https://www.yourdomain.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your-vercel-project.vercel.app,https://www.yourdomain.com` |
| `FRONTEND_BASE_URL` | `https://www.yourdomain.com` |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | SMTP hostname (e.g., `smtp.gmail.com`, `smtp.sendgrid.net`) |
| `EMAIL_PORT` | `587` (for STARTTLS) or `465` (for implicit TLS) |
| `EMAIL_HOST_USER` | Your SMTP username |
| `EMAIL_HOST_PASSWORD` | Your SMTP API key or password (keep secret) |
| `EMAIL_USE_TLS` | `true` (if EMAIL_PORT is 587) |
| `EMAIL_USE_SSL` | `false` (or `true` if EMAIL_PORT is 465 and EMAIL_USE_TLS is false) |
| `DEFAULT_FROM_EMAIL` | `EDUstacked <noreply@yourdomain.com>` |
| `PAYSTACK_SECRET_KEY` | `sk_test_...` for test mode; `sk_live_...` only after verified |
| `CBT_LICENSE_SIGNING_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `CBT_PACKAGE_SIGNING_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(64))"` |

Optional variables:
- `DJANGO_LOG_LEVEL`: `INFO` (or `DEBUG` for troubleshooting)
- `DB_CONN_MAX_AGE`: `60` (tune based on connection limits)
- `DB_CONNECT_TIMEOUT`: `5`
- `DJANGO_SECURE_HSTS_SECONDS`: `31536000` (only after HTTPS verified)
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`: `false`
- `DJANGO_SECURE_HSTS_PRELOAD`: `false`

## First Deployment

1. **Push to main:** Merge all changes to the `main` branch on GitHub.

2. **Trigger GitHub Actions:** Verify the production workflow completes successfully. This validates tests and creates a release package.

3. **Deploy to Railway:**
   - Set backend service source branch to `main`
   - Add/update all required environment variables
   - Deploy the backend service
   - Monitor logs during deployment: Railway will run Pre-Deploy Command (migrations) before starting the app

4. **Verify Django Admin static assets:**
   - Visit `https://your-api-domain.railway.app/admin/`
   - If styled correctly (CSS/JS loaded), WhiteNoise is working
   - If unstyled (no CSS), check Railway logs for static file errors

5. **Test email delivery:**
   - Trigger a signup and verify the verification email arrives
   - Check SMTP settings if email does not arrive

6. **Test authentication flow:**
   - Login from the Vercel frontend → Refresh token → Logout
   - Confirm JWT tokens work across domains

7. **Test Paystack (test mode only):**
   - Attempt a test report-card credit purchase
   - Do NOT switch to live Paystack keys until this flow is verified

## Common Issues and Fixes

### "Pre-Deploy Command timed out"
- Migrations are taking too long (large database)
- Solution: Increase timeout in Railway Start Command `--timeout 120` or higher

### "Static files not loading / Admin is unstyled"
- WhiteNoise is not configured
- Solution: Verify `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"` in settings.py
- Run `python manage.py collectstatic` locally to verify it collects admin files

### "Email verification not sending"
- SMTP credentials are missing or incorrect
- Solution: Check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in Railway variables

### "Database connection refused"
- PostgreSQL service name in DATABASE_URL reference is wrong
- Solution: Check Railway PostgreSQL service name (usually `Postgres`), verify it matches `${{Postgres.DATABASE_URL}}`

### "CSRF token mismatch / Origin not allowed"
- DJANGO_CORS_ALLOWED_ORIGINS or DJANGO_CSRF_TRUSTED_ORIGINS is not set correctly
- Solution: Use exact frontend origin (include `https://`), no paths or trailing slashes

## Subsequent Deployments

1. **Make code changes** on the `main` branch
2. **Push to GitHub** → GitHub Actions runs tests and creates a release
3. **Railway auto-deploys** if configured with main branch as source
4. **Pre-Deploy Command** runs migrations automatically
5. **Monitor logs** for any errors

**Do NOT manually run migrations from the Railway CLI.** The Pre-Deploy Command is the single source of truth.

## Rollback Procedure

If a deployment fails:

1. Check Railway logs for the error
2. Fix the issue (code, migration, or configuration)
3. Commit and push to main
4. Railway redeploys automatically
5. Monitor the deployment

## Storage and Media Files

**Current limitation:** Media files (school logos, student photos, report-card PDFs) use local `MEDIA_ROOT` on the Railway instance. This is ephemeral and will be lost on redeploy or container restart.

**Action item:** Configure persistent object storage (e.g., AWS S3, Railway Volumes) before uploading production media. See `docs/object-storage-setup.md` (not yet written) for integration steps.

## Monitoring and Logs

- View Railway deployment logs in the dashboard
- Use Railway CLI: `railway logs`
- Check for startup errors in pre-deploy command output
- Monitor `/api/v1/health/database/` endpoint to confirm app is running
