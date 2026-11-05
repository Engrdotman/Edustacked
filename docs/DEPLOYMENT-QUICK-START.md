# EDUstacked Railway Deployment – Quick Start

This is a quick reference. For detailed setup, see `railway-deployment-checklist.md`.

## Status of Deployment Readiness

| Item | Status | Action |
|---|---|---|
| Gunicorn pinned | ✅ FIXED | Already in requirements.txt |
| WhiteNoise configured | ✅ FIXED | Middleware + storage configured |
| Email validation | ✅ FIXED | Production requires EMAIL_HOST_USER |
| Single migration path | ✅ FIXED | GitHub workflow no longer runs migrations |
| Object storage | ⚠️ TODO | Configure S3/Volumes before uploading media |
| CBT entitlements | ⚠️ TODO | Block CBT sales until fulfillment implemented |

## Next Railway Deploy (3 Steps)

### Step 1: Set Backend Service Configuration

| Setting | Value |
|---|---|
| Root Directory | `/backend` |
| Build Command | `python -m pip install --upgrade pip && python -m pip install -r requirements.txt` |
| Pre-Deploy Command | `python manage.py migrate --noinput` |
| Start Command | `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Healthcheck Path | `/api/v1/health/database/` |

### Step 2: Set Environment Variables

**Required:**
```
DJANGO_SECRET_KEY=<new-unique-secret>
DJANGO_DEBUG=false
DATABASE_URL=${{Postgres.DATABASE_URL}}
DJANGO_ALLOWED_HOSTS=your-api.railway.app,api.yourdomain.com
DJANGO_CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://www.yourdomain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-frontend.vercel.app,https://www.yourdomain.com
FRONTEND_BASE_URL=https://www.yourdomain.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com (or your provider)
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
PAYSTACK_SECRET_KEY=sk_test_... (test mode)
CBT_LICENSE_SIGNING_KEY=<new-unique-secret>
CBT_PACKAGE_SIGNING_KEY=<new-unique-secret>
```

**Optional:**
```
DJANGO_LOG_LEVEL=INFO
DB_CONN_MAX_AGE=60
DJANGO_SECURE_HSTS_SECONDS=31536000 (only after HTTPS verified)
```

To generate secrets locally:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Step 3: Deploy

1. Ensure backend source branch is set to `main` (or `develop` for staging)
2. Click "Deploy" in Railway dashboard
3. Monitor logs during deployment
4. Verify health check: `curl https://your-api.railway.app/api/v1/health/database/`
5. Check Django admin: `https://your-api.railway.app/admin/` (should be styled with CSS)

## Verification Checklist

- [ ] App deployed without errors (check logs)
- [ ] Health check passes: `GET /api/v1/health/database/` returns 200
- [ ] Django admin styled (CSS loaded): `GET /admin/`
- [ ] Signup triggers verification email (check inbox)
- [ ] Login, refresh token, logout work
- [ ] Paystack test-mode purchase works (do NOT use live mode yet)

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| "Email verification not sent" | SMTP not configured | Set EMAIL_HOST_USER and PASSWORD |
| "Static files not loading" | WhiteNoise not configured | Already fixed in this update |
| "Migration failed" | Wrong DATABASE_URL | Verify `${{Postgres.DATABASE_URL}}` reference |
| "CORS error" | Wrong DJANGO_CORS_ALLOWED_ORIGINS | Use exact frontend origin (with https://) |
| "Health check fails" | Database connection issue | Check DATABASE_URL and PostgreSQL service name |

## Before Selling Features

- ✅ Report-card credits: Can sell now (Paystack flow works)
- ❌ CBT licenses: Block sales until entitlements implemented (see `cbt-payment-fulfillment.md`)

## Media Files Important Note

Current deployment stores files in app container (ephemeral). Before uploading real data:
1. Read `docs/media-storage-setup.md`
2. Configure S3 or Railway Volumes
3. Update Django storage settings
4. Test file upload/download

**Do NOT store school logos or student data on ephemeral storage.**

## Full Documentation

- Setup: `docs/railway-deployment-checklist.md`
- Troubleshooting: `docs/railway-deployment-checklist.md#common-issues-and-fixes`
- Storage options: `docs/media-storage-setup.md`
- CBT payments: `docs/cbt-payment-fulfillment.md`
- Architecture: `docs/railway-deployment-setup.md`

## Support

Railway logs: Backend service → Deployments → View logs  
Health endpoint: `https://your-api.railway.app/api/v1/health/database/`  
Contact: See `docs/railway-deployment-setup.md` for full contact settings.
