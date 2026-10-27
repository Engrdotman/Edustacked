# CI/CD Pipeline Setup

This document describes the automated CI/CD pipeline for Edustacked using GitHub Actions.

## Pipeline Overview

The CI/CD pipeline consists of multiple workflows triggered on different events:

```
┌─────────────────┐
│  Code Push      │
└────────┬────────┘
         │
         ├──────────────────┬──────────────────┐
         │                  │                  │
    ┌────▼────┐      ┌──────▼───┐      ┌─────▼─────┐
    │ Linting │      │ Testing  │      │ Security  │
    └────┬────┘      └──────┬───┘      └─────┬─────┘
         │                  │                 │
         └──────────────────┼─────────────────┘
                            │
                    ┌───────▼────────┐
                    │ Quality Report │
                    └───────┬────────┘
                            │
                ┌───────────┴──────────────┐
                │                          │
         ┌──────▼──────┐           ┌──────▼──────┐
         │ develop     │           │ main        │
         │ → Staging   │           │ → Production│
         └─────────────┘           └─────────────┘
```

## Workflows

### 1. Backend Tests & Linting (`test-backend.yml`)

**Triggered on**:
- Push to `main` or `develop`
- Pull request to `main` or `develop`
- Changes in `backend/` directory

**Steps**:
1. Set up Python 3.12 with PostgreSQL service
2. Install dependencies
3. Run linting (flake8, black)
4. Run database migrations
5. Execute tests with coverage
6. Upload coverage to Codecov
7. Comment on PR with coverage report

**Environment Variables**:
```
DEBUG=False
SECRET_KEY=test-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/test_db
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### 2. Frontend Tests & Linting (`test-frontend.yml`)

**Triggered on**:
- Push to `main` or `develop`
- Pull request to `main` or `develop`
- Changes in `frontend/` directory

**Steps**:
1. Set up Node.js 18
2. Install dependencies with npm ci
3. Run linting checks
4. Build production bundle
5. Upload build artifacts

**Build artifacts**:
- Frontend distribution files stored for 5 days
- Used for staging/production deployment

### 3. Code Quality & Security (`code-quality.yml`)

**Triggered on**:
- Push to `main` or `develop`
- All pull requests

**Steps**:
1. Run Trivy vulnerability scanner
2. Upload results to GitHub Security tab
3. Check Python dependencies with Safety
4. Check Node dependencies with npm audit

**Reports Available**:
- Vulnerabilities in dependencies
- Security issues in code
- Integration with GitHub Security dashboard

### 4. Deploy to Staging (`deploy-staging.yml`)

**Triggered on**:
- Push to `develop` branch
- Manual workflow dispatch

**Environment**: `staging` (requires approval for secrets)

**Steps**:
1. Set up Python and Node.js
2. Install dependencies
3. Build frontend
4. Run database migrations
5. Send Slack notification

**Required Secrets**:
- `STAGING_API_URL`: Staging API endpoint
- `SECRET_KEY`: Django secret key
- `DATABASE_URL`: Staging database connection
- `ALLOWED_HOSTS`: Allowed hostnames
- `SLACK_WEBHOOK`: Slack notification webhook

### 5. Deploy to Production (`deploy-production.yml`)

**Triggered on**:
- Push to `main` branch
- Manual workflow dispatch

**Environment**: `production` (requires approval for secrets)

**Flow**:
1. Run all tests
2. Build frontend
3. Deploy (if tests pass)
4. Create release tag
5. Send Slack notification

**Required Secrets**:
- All production deployment credentials
- `SLACK_WEBHOOK`: Slack notification webhook

## Setting Up GitHub Actions

### Step 1: Enable GitHub Actions

1. Go to repository Settings
2. Navigate to Actions → General
3. Select "Allow all actions and reusable workflows"
4. Click Save

### Step 2: Configure Branch Protection Rules

#### For `main` branch:
1. Go to Settings → Branches
2. Click "Add rule"
3. Branch name pattern: `main`
4. Enable:
   - "Require a pull request before merging"
   - "Require approvals" (minimum 1)
   - "Dismiss stale pull request approvals"
   - "Require status checks to pass before merging"
   - "Require branches to be up to date"
   - "Restrict who can push to matching branches" (Admin)

Status checks to require:
- Backend Tests & Linting
- Frontend Tests & Linting
- Code Quality & Security

#### For `develop` branch:
1. Same as above but allow team members to push
2. Minimum 1 approval required

### Step 3: Add Repository Secrets

Go to Settings → Secrets and variables → Actions

**For Staging Environment** (`staging`):
```
STAGING_API_URL=https://api-staging.example.com
SECRET_KEY=<your-secret-key>
DATABASE_URL=postgresql://user:pass@host:5432/db
ALLOWED_HOSTS=staging.example.com
SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

**For Production Environment** (`production`):
```
SECRET_KEY=<your-production-secret-key>
DATABASE_URL=postgresql://user:pass@prod-host:5432/db
ALLOWED_HOSTS=example.com,www.example.com
SLACK_WEBHOOK=https://hooks.slack.com/services/...
PRODUCTION_DEPLOY_KEY=<your-deploy-key>
```

### Step 4: Add Environments (Optional but Recommended)

1. Go to Settings → Environments
2. Create "staging" environment
3. Create "production" environment
4. Add environment-specific secrets
5. Configure required reviewers for production

## Monitoring Workflows

### View Workflow Runs

1. Go to Actions tab in GitHub
2. Select workflow from left sidebar
3. See all runs with status and duration

### Check Logs

1. Click on a workflow run
2. Click on the job to see logs
3. Expand failed steps for error details

### PR Status Checks

1. Open pull request
2. Scroll to bottom
3. See status of all checks
4. Click "Details" to see full logs

## Troubleshooting

### Workflow Not Triggering

1. Check workflow file syntax (valid YAML)
2. Verify branch name matches trigger conditions
3. Ensure file changes match the `paths` filter
4. Check Actions tab for disabled workflows

### Test Failures

1. Check test logs in Actions tab
2. Reproduce locally:
   ```bash
   # Backend
   cd backend && pytest
   
   # Frontend
   cd frontend && npm run build
   ```
3. Fix issues and push again

### Secret-Related Errors

1. Verify secrets are added in Settings → Secrets
2. Check secret names match workflow file
3. Ensure secrets are not accidentally logged
4. For organization secrets, verify repository has access

### Permission Errors

1. Check GitHub token has necessary permissions
2. For deployment workflows, verify deployment keys are valid
3. Ensure service account has required access

## Notifications

### Slack Integration

Workflows can send notifications to Slack:

1. Create Slack webhook URL
2. Add as secret: `SLACK_WEBHOOK`
3. Messages include:
   - Workflow status (✅ success, ❌ failure)
   - Repository and branch
   - Commit message and author
   - Links to workflow run

### Email Notifications

GitHub automatically sends email on:
- Workflow failure
- Required review on deployment
- Security alerts

Configure in Settings → Notifications

## Performance Optimization

### Cache Dependencies

Workflows already cache:
- Python pip dependencies
- Node.js npm packages

This reduces installation time by ~60%

### Parallel Jobs

- Backend and frontend tests run in parallel
- Reduces total pipeline duration

### Artifact Storage

- Frontend build artifacts stored 5 days
- Reduces re-build time if needed

## Best Practices

1. **Keep workflows updated**: Review and update tools regularly
2. **Use specific versions**: Pin action versions for consistency
3. **Fail fast**: Lint before testing, test before deploy
4. **Clear logs**: Use descriptive step names
5. **Monitor costs**: GitHub Actions has usage limits
6. **Security first**: Never log secrets, use GitHub Secrets
7. **Document changes**: Update this file when modifying workflows

## Cost Estimation

GitHub Actions free tier includes:
- 2,000 minutes/month for private repos
- 10GB artifact storage

Estimated usage for this project:
- ~100 PR runs/month: ~500 minutes
- ~10 deployments/month: ~200 minutes
- Total: ~700 minutes/month ✅ Within free tier

## Next Steps

1. Create `develop` branch: `git checkout -b develop && git push origin develop`
2. Configure branch protection rules
3. Add secrets for staging/production
4. Create first feature branch and open PR
5. Monitor workflow runs
6. Adjust thresholds and requirements as needed
