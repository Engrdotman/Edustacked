# Render Deployment Guide

This document explains how to deploy the EDUstacked frontend on Render.

## Prerequisites

- Render account (https://render.com)
- GitHub repository connected to Render
- Backend API running on Railway (or another host)

## Deployment Steps

### 1. Create a Render Blueprint

The repository now has a root-level `render.yaml`. In the Render dashboard choose **New + → Blueprint**, connect this repository, and select the branch to deploy. The Blueprint sets the service root to `frontend`, installs the locked npm dependencies, builds the app, and starts the Express server.

If creating a Web Service manually, use these settings:

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Runtime | Node |
| Build command | `npm ci && npm run build` |
| Start command | `npm start` |

### 2. Set Environment Variables

The Blueprint sets the backend destination. For a manually created service, add this server-side environment variable:

```
API_BACKEND_URL=https://edustacked-production.up.railway.app
```

(Replace with your actual backend API URL if different. Do not add a trailing `/api`.)

After Render assigns the service URL, set `FRONTEND_BASE_URL` on the Railway backend to that exact HTTPS origin (no trailing slash). This controls parent activation links and adds the Render origin to Django's CSRF trusted origins. Keep the API's own `DJANGO_ALLOWED_HOSTS` set to its backend host. The browser calls Render's same-origin `/api` proxy; it does not need direct cross-origin access to Railway.

### 3. Deploy

Render will automatically build and deploy when:
- You connect the GitHub repo (initial deployment)
- You push changes to the connected branch

## How It Works

The frontend deployment includes:

- **Vite Build**: Compiles React app to optimized static files in `dist/`
- **Express Server** (`server.js`): Serves static files and proxies API calls
- **API Proxy**: Routes `/api/*` requests to Railway using the server-only `API_BACKEND_URL`
- **SPA Routing**: Non-API routes serve `index.html` for React Router support
- **Cache Headers**: Properly caches static assets while keeping HTML fresh

## Troubleshooting

### 404 Errors on Sign-In

**Issue**: `/api/v1/auth/csrf/` returns 404

**Check:**
1. Verify `API_BACKEND_URL` is set to the Railway backend origin, without a trailing `/api`
2. Check that your Railway backend is running and accessible
3. Look at the server logs in the Render dashboard; startup logs show the backend origin and proxy failures show the requested path/status
4. Test the backend URL directly: `https://your-backend-url.app/api/v1/auth/csrf/`

### Static Files Not Loading

**Issue**: CSS, JS, or images return 404

**Check:**
1. Verify build completed successfully: Check "Build Logs" in Render
2. Ensure `dist/` folder was created with files
3. Check the `npm run build` command output

### Sign-in or activation-link issues

**Issue**: Sign-in fails, or parent activation links point to the wrong site

**Check:** Set `FRONTEND_BASE_URL` on Railway to the exact Render service origin (or custom domain). The frontend calls the API through its same-origin proxy, so browser requests should not need direct cross-origin access to Railway. Django uses this origin when creating guardian links and CSRF trust.

### Service Won't Start

**Issue**: Service shows as failed or keeps restarting

**Check:**
1. Click service → "Logs" to see startup errors
2. Verify all dependencies are in `package.json`
3. Ensure `dist/` folder is built before server starts
4. Check for missing environment variables

## Logs and Debugging

To view logs:
1. Go to your service in the Render dashboard
2. Click the "Logs" tab
3. Look for errors in the output

For more detailed debugging, add logging to `server.js` and push changes.

## Performance

- **Static file caching**: 1 hour for assets, no-cache for HTML
- Render's free web services spin down after 15 minutes without inbound traffic, so the first request after idle can be slow. Render says free instances are for testing/hobby use, not production; use a paid instance before relying on this frontend for time-sensitive school payments. See [Render's free service limits](https://render.com/docs/free).

## Redeploy

To redeploy without code changes:
1. Go to service page
2. Click "Redeploy"

The build will run again with current code.
