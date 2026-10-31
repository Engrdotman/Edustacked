# EDUstacked

A thoughtful foundation for the everyday work of school communities. Built to grow with your school, one useful step at a time.

## Overview

EDUstacked is a modular school management platform with a Django REST API backend and a React frontend. Schools can register, verify their administrator email, and begin a guided setup while platform administrators review school legitimacy separately. School workflow modules are developed incrementally.

See [Hybrid School Onboarding](docs/hybrid-school-onboarding.md) for the registration lifecycle, verification model, ownership, platform review, tenant isolation, and local testing walkthrough.

## Project Structure

```
Edustacked/
├── backend/                  # Django REST API
│   ├── apps/
│   │   ├── accounts/        # User authentication and management
│   │   ├── schools/         # School and membership management
│   │   └── core/            # Core functionality
│   ├── config/              # Django configuration
│   ├── manage.py
│   └── requirements.txt
├── frontend/                # React application
│   ├── src/
│   │   ├── pages/          # Page components
│   │   ├── components/     # Reusable components
│   │   ├── services/       # API services
│   │   ├── auth/           # Authentication context
│   │   └── styles/         # Styling
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docs/                    # Documentation
│   ├── BRANCHING-STRATEGY.md
│   ├── CI-CD-SETUP.md
│   ├── architecture.md
│   └── ...
└── .github/                 # GitHub configuration
    ├── workflows/          # CI/CD pipelines
    ├── pull_request_template.md
    └── CODEOWNERS
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Git
- Virtual Environment (recommended)

### Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

Backend will be available at: `http://localhost:8000`

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Create .env file
cp .env.example .env

# Start development server
npm run dev
```

Frontend will be available at: `http://localhost:5173`

## API Documentation

The API uses Django REST Framework. Key endpoints:

- `/api/v1/auth/` - Authentication and memberships
- `/api/v1/schools/` - School profile, settings, and membership management
- `/api/v1/health/` - API health check

Full API documentation available at `/api/docs/` when backend is running.

Module 3 profile, settings, and protected logo endpoints are documented in [School Profile and Settings](docs/school-profile-and-settings.md).

Module 4 academic sessions, terms, classes, subjects, and grading configuration are documented in [Academic Setup](docs/academic-setup.md).

## Development Workflow

See [BRANCHING-STRATEGY.md](docs/BRANCHING-STRATEGY.md) for detailed development workflow and branching strategy.

### Quick Summary:
1. Create feature branch: `git checkout -b feature/SMS-123-feature-name`
2. Make changes and commit: `git commit -m "feat: description"`
3. Push to GitHub: `git push origin feature/SMS-123-feature-name`
4. Open pull request to `develop` branch
5. After review and approval, merge to `develop`
6. Automated tests and staging deployment run

## CI/CD Pipeline

The project uses GitHub Actions for automated:
- ✅ Code linting (flake8, black, eslint)
- ✅ Unit testing (pytest for backend, vitest for frontend)
- ✅ Security scanning (Trivy, dependency checks)
- ✅ Coverage reporting
- ✅ Automated deployment to staging and production

See [CI-CD-SETUP.md](docs/CI-CD-SETUP.md) for full documentation.

## Testing

### Backend Tests

```bash
cd backend
pytest                          # Run all tests
pytest apps/accounts/tests.py   # Run specific tests
pytest --cov=apps              # Run with coverage
```

### Frontend Tests

```bash
cd frontend
npm run test                    # Run tests
npm run test:watch             # Watch mode
```

## Project Documentation

- [Architecture](docs/architecture.md) - System design and components
- [Database Schema](docs/database-schema.md) - Data model documentation
- [School Profile and Settings](docs/school-profile-and-settings.md) - Module 3 API, permissions, storage, and manual checks
- [Academic Setup](docs/academic-setup.md) - Module 4 models, API, lifecycle rules, and manual walkthrough
- [Student Management](docs/student-management.md) - Module 5 admissions, guardians, enrollment history, security, and acceptance checklist
- [Staff Management](docs/staff-management.md) - Module 6 employment profiles, teacher designations, assignments, and RBAC rules
- [Student Attendance](docs/student-attendance.md) - Module 7 register workflow, enrollment snapshots, teacher scope, reporting rules, and API
- [Assessments and Results](docs/assessment-results.md) - Module 8 assessment plans, score calculations, approval workflow, and API
- [Report Cards](docs/report-cards.md) - Module 9 generation, validation, review, immutable revisions, attendance policy, and secured PDFs
- [Report-card Credits and Billing](docs/billing-and-credits.md) - Module 10 credit rules, Paystack setup, tenant APIs, and reconciliation
- [Parent and Guardian Portal](docs/parent-guardian-portal.md) - Module 11 activation, linked-student access, attendance, report cards, announcements, and notifications
- [School Reports and Analytics](docs/school-reports-and-analytics.md) - Module 12 role-scoped dashboards, metric definitions, filters, and safe CSV exports
- [Development Setup](docs/development-setup.md) - Detailed setup instructions
- [Branching Strategy](docs/BRANCHING-STRATEGY.md) - Git workflow and conventions
- [CI/CD Setup](docs/CI-CD-SETUP.md) - GitHub Actions configuration
- [Module Roadmap](docs/module-roadmap.md) - Planned features and modules

## Technology Stack

### Backend
- **Framework**: Django 5.2
- **API**: Django REST Framework 3.16
- **Database**: SQLite for development; PostgreSQL for deployment
- **Authentication**: JWT (djangorestframework-simplejwt)
- **Security**: CORS headers, environment variables

### Frontend
- **Framework**: React 19
- **Build Tool**: Vite 6
- **Styling**: CSS (custom)
- **HTTP Client**: Fetch API

## Environment Configuration

### Backend `.env`
```
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://user:password@localhost/edustacked
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### Frontend `.env`
```
VITE_API_URL=http://localhost:8000
```

## Contributing

1. Read [BRANCHING-STRATEGY.md](docs/BRANCHING-STRATEGY.md)
2. Create feature branch
3. Make changes with clear commits
4. Write tests for new features
5. Ensure all checks pass
6. Submit pull request with description

## Code Quality Standards

- **Python**: Black formatting, flake8 linting
- **JavaScript**: Standard conventions
- **Documentation**: Clear docstrings and comments
- **Tests**: Minimum 80% coverage for new code
- **Commits**: Conventional commit messages

## Support & Contact

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing documentation
- Review previous pull requests

## License

[Add your license information]

## Changelog

See [releases](https://github.com/Engrdotman/Edustacked/releases) for version history and updates.

---

**Made for the people who make a school.** 🏫
