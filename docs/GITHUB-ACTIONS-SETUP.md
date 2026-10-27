# GitHub Actions Setup Instructions

Complete setup guide to enable CI/CD pipelines and branch protection for Edustacked.

## Step 1: Enable GitHub Actions

1. Go to your repository: https://github.com/Engrdotman/Edustacked
2. Navigate to **Settings** → **Actions** → **General**
3. Under "Actions permissions", select: **"Allow all actions and reusable workflows"**
4. Click **Save**

## Step 2: Configure Branch Protection Rules

### Protect `main` Branch (Production)

1. Go to **Settings** → **Branches**
2. Click **Add rule**
3. Fill in branch name pattern: `main`
4. Enable the following:
   - ✅ **Require a pull request before merging**
     - Require approvals: `1`
     - Dismiss stale pull request approvals when new commits are pushed
   - ✅ **Require status checks to pass before merging**
     - Require branches to be up to date before merging
     - Select required status checks:
       - `Backend Tests & Linting`
       - `Frontend Tests & Linting`
       - `Code Quality & Security`
   - ✅ **Restrict who can push to matching branches**
     - Select: Administrators only
5. Click **Create**

### Protect `develop` Branch (Staging)

1. Go to **Settings** → **Branches**
2. Click **Add rule**
3. Fill in branch name pattern: `develop`
4. Enable the following:
   - ✅ **Require a pull request before merging**
     - Require approvals: `1`
   - ✅ **Require status checks to pass before merging**
     - Require branches to be up to date before merging
     - Select required status checks:
       - `Backend Tests & Linting`
       - `Frontend Tests & Linting`
5. Click **Create**

## Step 3: Add Repository Secrets

### For Staging Environment

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each:

```
Name: STAGING_API_URL
Value: https://api-staging.example.com
```

```
Name: SLACK_WEBHOOK
Value: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

> Optional: Add other staging-specific secrets as needed

### For Production Environment

1. Same location as above, add:

```
Name: SECRET_KEY
Value: <your-django-secret-key>
```

```
Name: DATABASE_URL
Value: postgresql://user:password@host:5432/database
```

```
Name: ALLOWED_HOSTS
Value: example.com,www.example.com
```

```
Name: SLACK_WEBHOOK
Value: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

> ⚠️ Never commit secrets. Keep them in GitHub Secrets only.

## Step 4: Create Environments (Recommended)

This adds an extra layer of security for production deployments.

### Create Staging Environment

1. Go to **Settings** → **Environments**
2. Click **New environment**
3. Name: `staging`
4. Optionally configure:
   - Deployment branches: `develop`
   - Required reviewers: (leave empty for auto-deployment)

### Create Production Environment

1. Go to **Settings** → **Environments**
2. Click **New environment**
3. Name: `production`
4. Configure:
   - Deployment branches: `main`
   - Required reviewers: Check your GitHub username
   - Select: "Protect this environment"
5. Click **Create environment**

This ensures production deployments require manual approval.

## Step 5: Configure Slack Notifications (Optional)

### Get Slack Webhook URL

1. Go to [Slack API](https://api.slack.com/apps)
2. Create New App → From scratch
3. Give it a name, select your workspace
4. Go to **Incoming Webhooks**
5. Click **Create New Webhook**
6. Select your desired channel
7. Copy the Webhook URL

### Add to GitHub

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add new secret:
   - Name: `SLACK_WEBHOOK`
   - Value: Paste the webhook URL

Now GitHub Actions will send notifications to your Slack channel.

## Step 6: Test the Setup

### Trigger the Workflows

1. Create a test feature branch:
   ```bash
   git checkout -b feature/test-ci-cd
   ```

2. Make a small change (e.g., add a comment)

3. Push and create a PR:
   ```bash
   git push origin feature/test-ci-cd
   ```

4. Go to GitHub and create a pull request to `develop`

### Monitor the Workflows

1. Go to **Actions** tab
2. You should see workflows running:
   - Backend Tests & Linting
   - Frontend Tests & Linting
   - Code Quality & Security

3. Wait for them to complete
4. Check PR for status indicators

## Step 7: Verify Branch Protection

1. Try to merge the PR without approval
2. GitHub should prevent it with message: "Review required"
3. Try to merge with failing tests
4. GitHub should show: "Status check failure"

## Troubleshooting

### Workflows Not Running

**Problem**: Workflows don't start when pushing code

**Solution**:
1. Check that GitHub Actions are enabled
2. Verify workflow files are in `.github/workflows/`
3. Check workflow syntax (YAML must be valid)
4. Ensure branch name matches workflow trigger

### Tests Failing on GitHub but Pass Locally

**Problem**: CI reports test failure even though tests pass locally

**Solutions**:
1. Check environment variables in workflow vs local setup
2. Verify Python/Node.js versions match
3. Check database configuration
4. Look at detailed logs in Actions tab

### Status Checks Not Appearing

**Problem**: Required status checks not showing in PR

**Solution**:
1. Go to **Settings** → **Branches**
2. Edit the branch rule
3. Click "Refresh" next to status checks
4. Re-select required checks from the list

### Secrets Not Working

**Problem**: Workflows fail with "permission denied" or similar

**Solutions**:
1. Verify secret names match exactly in workflow files
2. Check that secrets are added to correct scope (repository vs environment)
3. Ensure secret values don't have trailing whitespace
4. For production, verify environment-specific secrets are set

### Cannot Push to Protected Branch

**Problem**: "permission denied" when trying to push to `main`

**Expected behavior**: This is correct for `main` branch. Use this workflow:
1. Create feature branch from `develop`
2. Push feature branch
3. Create PR to `develop`
4. After merge to `develop`, the changes are staged
5. Release branch goes to `main` after approval

## Workflow Overview

### Development Flow

```
1. Create feature branch from develop
   └─► feature/SMS-123-feature-name

2. Push and create PR to develop
   └─► All checks run

3. On PR approval and checks passing
   └─► Merge to develop

4. Automatic deployment to staging
   └─► Smoke tests run

5. Create release PR from develop to main
   └─► Final review

6. On approval to main
   └─► Production deployment
   └─► Release tag created
```

### GitHub Actions Triggers

| Event | Trigger | Runs |
|-------|---------|------|
| PR opened to `develop` | Pull request | All tests |
| Push to `develop` | Code merged | Tests + Staging deploy |
| PR opened to `main` | Pull request | All tests |
| Push to `main` | Release merge | Tests + Production deploy |

## Next Steps

1. ✅ Set up branch protection rules
2. ✅ Add required secrets
3. ✅ Create staging and production environments
4. ✅ Test with a feature branch
5. ✅ Monitor first workflows
6. ✅ Share branching strategy with team

## Quick Reference

### Common Commands

```bash
# Start new feature
git checkout develop
git pull origin develop
git checkout -b feature/SMS-123-feature-name
git push -u origin feature/SMS-123-feature-name

# Update branch with latest develop
git fetch origin
git rebase origin/develop
git push -f origin feature/SMS-123-feature-name

# After PR is merged
git checkout develop
git pull origin develop
# Feature branch auto-deletes on GitHub (set in settings)

# Create hotfix (urgent production fix)
git checkout main
git pull origin main
git checkout -b hotfix/SMS-999-critical-issue
git push -u origin hotfix/SMS-999-critical-issue
# Create PR to main for quick deployment
```

## Need Help?

- Check [BRANCHING-STRATEGY.md](./BRANCHING-STRATEGY.md) for workflow details
- See [CI-CD-SETUP.md](./CI-CD-SETUP.md) for technical workflow documentation
- Review GitHub Actions logs in Actions tab for specific errors
- Check each workflow file in `.github/workflows/` for step details

---

**🚀 Your CI/CD pipeline is now ready for automated testing and deployment!**
