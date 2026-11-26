# Render Deployment Guide

This document explains how to deploy the EDUstacked frontend on Render.

## Prerequisites

- Render account (https://render.com)
- GitHub repository connected to Render
- Backend API running on Railway (or another host)

## Deployment Steps

### 1. Create a New Web Service on Render

1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select the repository and choose branch (usually `main` or `develop`)

### 2. Configure the Service

**Basic Settings:**
- **Name**: `edustacked-frontend` (or your preferred name)
- **Environment**: `Node`
- **Build Command**: `npm run build`
- **Start Command**: `npm start`
- **Plan**: Free tier is fine for testing

### 3. Set Environment Variables

Add the following environment variable in the Render dashboard:

```
VITE_API_BASE_URL=https://edustacked-production.up.railway.app
```

(Replace with your actual backend API URL if different)

### 4. Deploy

Render will automatically build and deploy when:
- You connect the GitHub repo (initial deployment)
- You push changes to the connected branch

## How It Works

The frontend deployment includes:

- **Vite Build**: Compiles React app to optimized static files in `dist/`
- **Express Server** (`server.js`): Serves static files and proxies API calls
- **API Proxy**: Routes `/api/*` requests to your Railway backend
- **SPA Routing**: Non-API routes serve `index.html` for React Router support
- **Cache Headers**: Properly caches static assets while keeping HTML fresh

## Troubleshooting

### 404 Errors on Sign-In

**Issue**: `/api/v1/auth/csrf/` returns 404

**Check:**
1. Verify `VITE_API_BASE_URL` environment variable is set correctly
2. Check that your Railway backend is running and accessible
3. Look at the server logs in the Render dashboard
4. Test the backend URL directly: `https://your-backend-url.app/api/v1/auth/csrf/`

### Static Files Not Loading

**Issue**: CSS, JS, or images return 404

**Check:**
1. Verify build completed successfully: Check "Build Logs" in Render
2. Ensure `dist/` folder was created with files
3. Check the `npm run build` command output

### CORS Issues

**Issue**: Browser console shows CORS errors

**Solution**: The backend should have CORS properly configured. Check:
1. `backend/config/settings.py` - `CORS_ALLOWED_ORIGINS` or similar
2. Backend should allow requests from your Render domain

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

- **Build time**: ~1-2 minutes
- **Static file caching**: 1 hour for assets, no-cache for HTML
- **Service memory**: Free tier has 0.5GB (sufficient for static hosting + proxy)

## Redeploy

To redeploy without code changes:
1. Go to service page
2. Click "Redeploy"

The build will run again with current code.
