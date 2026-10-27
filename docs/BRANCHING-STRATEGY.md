# Branching Strategy & Workflow

This document outlines the branching strategy and workflow for the Edustacked project to maintain code quality, facilitate collaboration, and enable efficient error tracking.

## Branch Types

### 1. **main** (Production Branch)
- **Purpose**: Production-ready code only
- **Protection**: Branch protected with required reviews and passing checks
- **Deployment**: Automatically deploys to production
- **Merging**: Only from `release/*` branches via pull request
- **Tag Format**: `v{major}.{minor}.{patch}` (semantic versioning)

### 2. **develop** (Integration Branch)
- **Purpose**: Integration branch for features and fixes
- **Deployment**: Automatically deploys to staging environment
- **Merging**: Feature and bugfix branches merged here
- **Status**: Pre-release code tested in staging

### 3. **feature/** (Feature Branches)
- **Naming Convention**: `feature/{ticket-id}-{short-description}`
- **Example**: `feature/SMS-123-user-authentication`
- **Base Branch**: Branch from `develop`
- **Merge**: Back to `develop` via pull request
- **Lifecycle**: Delete after merge

### 4. **bugfix/** (Bug Fix Branches)
- **Naming Convention**: `bugfix/{ticket-id}-{short-description}`
- **Example**: `bugfix/SMS-456-login-validation-error`
- **Base Branch**: Branch from `develop`
- **Merge**: Back to `develop` via pull request
- **Lifecycle**: Delete after merge

### 5. **hotfix/** (Production Hotfix Branches)
- **Naming Convention**: `hotfix/{ticket-id}-{short-description}`
- **Example**: `hotfix/SMS-789-critical-security-patch`
- **Base Branch**: Branch from `main`
- **Merge**: To both `main` and `develop`
- **Deployment**: Direct merge to `main` triggers production deployment

### 6. **release/** (Release Preparation Branches)
- **Naming Convention**: `release/v{version}`
- **Example**: `release/v1.0.0`
- **Base Branch**: Branch from `develop`
- **Purpose**: Final testing, version bumps, release notes
- **Merge**: To `main` and back to `develop`

## Workflow

### Creating a New Feature

```bash
# Update develop branch
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/SMS-123-new-feature

# Make commits
git commit -m "feat: description of changes"

# Push to remote
git push origin feature/SMS-123-new-feature
```

### Submitting a Pull Request

1. Push your branch to GitHub
2. Open pull request to `develop`
3. Fill in the PR template:
   - **Description**: What changes and why
   - **Type**: Feature/Bugfix/Refactor/Documentation
   - **Ticket**: Reference issue number (SMS-123)
   - **Testing**: How was this tested
   - **Screenshots**: If UI changes

### Review & Merge Process

1. **Code Review**: Minimum 1 approval required
2. **CI/CD Checks**: All automated tests must pass
3. **Code Quality**: No critical issues flagged
4. **Merge**: Squash commits for cleaner history

```bash
# Update your feature branch with latest develop
git fetch origin
git rebase origin/develop

# After approval and merge
git checkout develop
git pull origin develop

# Create new feature branch for next work
git checkout -b feature/SMS-124-next-feature
```

## Release Process

### Minor/Patch Release (from develop)

```bash
# Create release branch
git checkout develop
git pull origin develop
git checkout -b release/v1.0.0

# Bump version, update CHANGELOG
# Commit: "chore: bump version to 1.0.0"

git push origin release/v1.0.0
```

### Merge Release to Main

1. Create PR from `release/v1.0.0` to `main`
2. Get approval
3. Merge to `main` (creates automatic production deployment)
4. Create release tag: `v1.0.0`
5. Merge back to `develop` to keep version in sync

## Hotfix Process

```bash
# Create hotfix from main
git checkout main
git pull origin main
git checkout -b hotfix/SMS-789-critical-fix

# Make fix
git commit -m "fix: critical issue description"
git push origin hotfix/SMS-789-critical-fix

# Create PR to main (urgent review)
# After merge to main → production deployment
# Also merge to develop to keep in sync
```

## Commit Message Convention

Follow conventional commits for clarity and automation:

```
type(scope): subject

body

footer
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

**Examples**:
```
feat(auth): add two-factor authentication
fix(login): resolve session timeout issue
docs(api): update endpoint documentation
refactor(database): optimize query performance
```

## CI/CD Pipeline

### On Pull Request
- ✅ Run backend tests
- ✅ Run frontend tests
- ✅ Linting checks
- ✅ Security scanning
- ✅ Code coverage reporting
- ✅ Build verification

### On Push to develop
- ✅ All PR checks
- ✅ Deploy to staging environment
- ✅ Smoke tests on staging
- ✅ Slack notification

### On Push to main
- ✅ All PR checks
- ✅ Production deployment
- ✅ Health checks
- ✅ Release creation
- ✅ Slack notification

## Error Tracking & Monitoring

### During Development
- All PR checks must pass
- Coverage reports attached to PR
- Failed tests block merge

### In Staging
- Monitor staging logs for errors
- Run integration tests
- Performance benchmarks

### In Production
- Automated error reporting
- Performance monitoring
- User impact assessment
- Automatic rollback capability on critical errors

## Protected Branch Rules

### main branch
- ✅ Require pull request reviews (minimum 1)
- ✅ Require status checks to pass
- ✅ Require code to be up to date
- ✅ Dismiss stale reviews on new commits
- ✅ Restrict who can push (admin only)

### develop branch
- ✅ Require pull request reviews (minimum 1)
- ✅ Require status checks to pass
- ✅ Require code to be up to date

## Tips & Best Practices

1. **Small PRs**: Keep pull requests focused and small (< 400 lines)
2. **Frequent Commits**: Commit logical chunks with clear messages
3. **Update Before PR**: Always rebase with latest `develop` before PR
4. **Test Locally**: Run tests locally before pushing
5. **Clear Descriptions**: Write detailed PR descriptions
6. **Link Issues**: Always reference related issue numbers
7. **Timely Reviews**: Review PRs promptly to maintain flow
8. **Keep Branches Clean**: Delete merged branches to reduce clutter

## Troubleshooting

### Accidentally committed to develop?
```bash
git reset --soft HEAD~1  # Undo commit, keep changes
git stash               # Stash changes
git checkout -b feature/new-branch
git stash pop          # Restore changes to new branch
git commit -m "feat: description"
```

### Need to sync with latest develop?
```bash
git fetch origin
git rebase origin/develop
git push origin +feature/branch-name  # Force push if needed
```

### Created branch from wrong base?
```bash
git rebase --onto develop main feature/branch-name
git push origin +feature/branch-name
```
