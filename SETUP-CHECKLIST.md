# 🎯 CI/CD & Branching Setup Checklist

This checklist helps you complete the setup of CI/CD pipelines and branch protection for your Edustacked project.

## ✅ Completed (Already Done)

- [x] GitHub repository created: https://github.com/Engrdotman/Edustacked
- [x] Main branch pushed with initial code
- [x] Develop branch created and pushed
- [x] GitHub Actions workflow files created:
  - `.github/workflows/test-backend.yml`
  - `.github/workflows/test-frontend.yml`
  - `.github/workflows/code-quality.yml`
  - `.github/workflows/deploy-staging.yml`
  - `.github/workflows/deploy-production.yml`
- [x] Pull request template created: `.github/pull_request_template.md`
- [x] CODEOWNERS file created: `.github/CODEOWNERS`
- [x] Dependabot configuration created: `.github/dependabot.yml`
- [x] Documentation created:
  - `docs/BRANCHING-STRATEGY.md`
  - `docs/CI-CD-SETUP.md`
  - `docs/GITHUB-ACTIONS-SETUP.md`
  - `README.md` (updated)

## 📋 Configuration Tasks (Do These Now)

### Phase 1: Enable & Protect (15 minutes)

- [ ] **Enable GitHub Actions**
  - Go to: Settings → Actions → General
  - Select: "Allow all actions and reusable workflows"
  - Save changes
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 1

- [ ] **Protect main branch**
  - Go to: Settings → Branches → Add rule
  - Pattern: `main`
  - Enable:
    - ✓ Require pull request (1 approval)
    - ✓ Require status checks (all passing)
    - ✓ Restrict who can push (admin only)
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 2

- [ ] **Protect develop branch**
  - Go to: Settings → Branches → Add rule
  - Pattern: `develop`
  - Enable:
    - ✓ Require pull request (1 approval)
    - ✓ Require status checks (all passing)
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 2

### Phase 2: Security & Secrets (10 minutes)

- [ ] **Add staging secrets** (if deploying to staging)
  - Go to: Settings → Secrets and variables → Actions
  - Add: `STAGING_API_URL`
  - Add: `SLACK_WEBHOOK` (optional, for notifications)
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 3

- [ ] **Add production secrets** (for production deployment)
  - Go to: Settings → Secrets and variables → Actions
  - Add: `SECRET_KEY`
  - Add: `DATABASE_URL`
  - Add: `ALLOWED_HOSTS`
  - Add: `SLACK_WEBHOOK` (optional)
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 3

### Phase 3: Environments (Optional, 5 minutes)

- [ ] **Create staging environment**
  - Go to: Settings → Environments → New environment
  - Name: `staging`
  - Set deployment branches: `develop`
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 4

- [ ] **Create production environment**
  - Go to: Settings → Environments → New environment
  - Name: `production`
  - Set deployment branches: `main`
  - Enable required reviewers: Your GitHub username
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 4

### Phase 4: Testing (10 minutes)

- [ ] **Test with feature branch**
  ```bash
  git checkout develop
  git pull origin develop
  git checkout -b feature/TEST-001-test-ci
  echo "# Test" >> README.md
  git add .
  git commit -m "feat: test CI/CD pipeline"
  git push -u origin feature/TEST-001-test-ci
  ```
  - Reference: `docs/GITHUB-ACTIONS-SETUP.md` Step 6

- [ ] **Create pull request**
  - Go to GitHub and create PR from your feature branch to `develop`
  - Reference: `docs/BRANCHING-STRATEGY.md` Submitting a Pull Request

- [ ] **Monitor workflows**
  - Go to Actions tab
  - Watch for workflow runs:
    - Backend Tests & Linting
    - Frontend Tests & Linting
    - Code Quality & Security
  - All should pass ✅

- [ ] **Verify branch protection**
  - Try to merge without approval (should fail)
  - Get approval and merge
  - Verify it succeeds

## 🎓 Learning Resources

### Quick Reads (5-10 minutes each)
- [ ] Read: `docs/BRANCHING-STRATEGY.md` - Learn the branching model
- [ ] Read: `SETUP-CHECKLIST.md` - This file
- [ ] Reference: `.github/pull_request_template.md` - PR format

### Complete Documentation (20-30 minutes)
- [ ] Read: `docs/CI-CD-SETUP.md` - Technical workflow details
- [ ] Read: `docs/GITHUB-ACTIONS-SETUP.md` - Step-by-step setup
- [ ] Read: `README.md` - Project overview

### Team onboarding
- [ ] Share this checklist with team members
- [ ] Share `docs/BRANCHING-STRATEGY.md` as team standard
- [ ] Discuss PR review expectations

## 🚀 Your First Workflow

### Day 1: Setup Complete ✅
1. [ ] Run through configuration tasks above
2. [ ] Verify with test feature branch
3. [ ] All workflows passing

### Day 2+: Start Development
1. [ ] Create feature branches for actual work
2. [ ] Follow commit conventions: `feat:`, `fix:`, `docs:`
3. [ ] Open PRs to `develop`
4. [ ] Get review and approval
5. [ ] Watch auto-deployment to staging
6. [ ] When ready, create release to `main`

## 📝 Quick Reference

### Common Git Commands

```bash
# Create feature
git checkout develop
git pull origin develop
git checkout -b feature/SMS-123-description

# Commit with conventional message
git commit -m "feat: add new feature"

# Push to GitHub
git push -u origin feature/SMS-123-description

# Update with latest develop
git fetch origin
git rebase origin/develop
git push -f origin feature/SMS-123-description

# After approval, merge in GitHub UI
# Then delete branch

# Pull latest develop
git checkout develop
git pull origin develop
```

### PR Checklist Before Submitting
- [ ] Branch created from latest `develop`
- [ ] All local tests passing
- [ ] Code formatted and linted
- [ ] Commit messages follow conventions
- [ ] Branch name follows pattern: `feature/SMS-123-description`
- [ ] PR description filled in from template
- [ ] Linked to related issues/tickets

### Troubleshooting

**Workflows not running?**
- Check: Actions tab → workflow name
- Verify: Workflow file syntax is valid YAML
- Check: Branch name matches trigger condition
- Enable: GitHub Actions in Settings

**Tests failing in CI but passing locally?**
- Check: Environment variables match
- Verify: Python/Node versions match
- Check: Database configuration
- View: Detailed logs in Actions tab

**Cannot push to main?**
- Expected: Branch protection prevents direct push
- Correct flow: Feature → PR to develop → release to main
- Never: Force push to main

## 🎉 Success Indicators

You'll know everything is working when:

1. ✅ You can create a feature branch
2. ✅ Workflows automatically run on push
3. ✅ PR shows all checks passing
4. ✅ You can't merge without approval
5. ✅ After merge, staging auto-deploys
6. ✅ Slack notifications arrive (if configured)
7. ✅ Release to main triggers production deploy

## 📞 Need Help?

1. **Setup Issues?** → See `docs/GITHUB-ACTIONS-SETUP.md`
2. **Workflow Questions?** → See `docs/CI-CD-SETUP.md`
3. **Branching Questions?** → See `docs/BRANCHING-STRATEGY.md`
4. **Still Stuck?** → Check GitHub Actions logs for error details

## 🎯 Next Steps After Setup

1. Create `.env` files for local development
2. Set up local development environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   python manage.py migrate
   
   # In another terminal:
   cd frontend
   npm install
   npm run dev
   ```
3. Create your first feature branch
4. Make a real PR and test the full workflow
5. Onboard team members with this checklist

---

**Status: Ready for Configuration** 🚀

**Estimated time to complete:** 30-45 minutes

**Questions?** Check the documentation files or GitHub Actions logs for details.
