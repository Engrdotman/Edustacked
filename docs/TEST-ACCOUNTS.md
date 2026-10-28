# Test Accounts & Development Credentials

This document provides information about test user accounts for development and testing of the Edustacked platform.

## Overview

Test accounts are pre-configured in the development database for manual testing, QA, and demonstration purposes. All test accounts use the domain `@edustacked.test` and are assigned to two test schools.

## Test User Accounts

### School Admin - North School
**Email:** `academic-admin@edustacked.test`  
**Password:** `admin@123`  
**Role:** School Admin  
**School:** EDUstacked Test School North  
**Permissions:** Full administrative access to school

### School Manager - North School
**Email:** `academic-manager@edustacked.test`  
**Password:** `manager@123`  
**Role:** School Manager  
**School:** EDUstacked Test School North  
**Permissions:** Management access (limited admin)

### Teacher - North School
**Email:** `academic-teacher@edustacked.test`  
**Password:** `teacher@123`  
**Role:** Teacher  
**School:** EDUstacked Test School North  
**Permissions:** Teacher-level access

### Receptionist - North School
**Email:** `academic-receptionist@edustacked.test`  
**Password:** `receptionist@123`  
**Role:** Receptionist / Front Desk  
**School:** EDUstacked Test School North  
**Permissions:** Reception and administrative support

### Accountant - North School
**Email:** `academic-accountant@edustacked.test`  
**Password:** `accountant@123`  
**Role:** Accountant  
**School:** EDUstacked Test School North  
**Permissions:** Financial and accounting access

### Outside Admin - South School
**Email:** `academic-outsider@edustacked.test`  
**Password:** `outsider@123`  
**Role:** School Admin  
**School:** EDUstacked Test School South  
**Permissions:** Full administrative access to different school

## Test Schools

### North School
- **Name:** EDUstacked Test School North
- **Slug:** edustacked-test-school-north
- **Status:** Active
- **Members:** 5 test users (see above)

### South School
- **Name:** EDUstacked Test School South
- **Slug:** edustacked-test-school-south
- **Status:** Active
- **Members:** 1 test user (academic-outsider)

## Testing Common Flows

### Test 1: Basic Login
1. Go to the login page
2. Enter: `academic-admin@edustacked.test`
3. Enter password: `admin@123`
4. You should be logged in as the admin

### Test 2: Multi-School Navigation
1. Login as admin: `academic-admin@edustacked.test` / `admin@123`
2. You have access to North School
3. Switch to outsider account to access South School
4. Both schools should display separately

### Test 3: Role-Based Access
1. Test different roles to verify permissions
2. Admin should see more options than teacher
3. Teacher should have limited functions
4. Each role should have appropriate access

### Test 4: Password Change
1. Login with any test account
2. Change the password
3. You will be logged out
4. Login with the new password to verify it works

## Resetting Test Accounts

If you need to reset test account passwords back to defaults, run:

```bash
cd backend
python create_test_accounts.py
```

This will:
- Reset all test account passwords to their defaults
- Create any missing test accounts
- Ensure proper school associations
- Display all current credentials

## Database Reset

To completely reset the database and recreate test accounts:

```bash
cd backend

# Delete the database
rm db.sqlite3

# Run migrations
python manage.py migrate

# Create test accounts and data
python create_test_accounts.py
```

## Important Notes

⚠️ **For Development Only**
- These credentials are only for development and testing
- Never use these accounts in production
- These accounts have no real personal data

🔒 **Security**
- Test passwords are simple and not secure
- All test accounts use public, known passwords
- Store actual production secrets in environment variables
- Use strong passwords for real user accounts

📝 **Adding More Test Data**
- Add schools through the admin panel or migrations
- Create new users by copying and modifying `create_test_accounts.py`
- Use Django shell for quick one-off account creation

## Authentication Details

### Login Flow
1. User enters email and password
2. Backend validates credentials against User model
3. Django's custom EmailBackend authenticates using `login_email` field
4. JWT tokens are generated (access + refresh)
5. Refresh token stored in HTTP-only cookie
6. Access token returned in response body

### Email Normalization
- Emails are automatically lowercased and trimmed
- `ACADEMIC-ADMIN@EDUSTACKED.TEST` = `academic-admin@edustacked.test`
- Login is case-insensitive

### Session Management
- Access tokens expire after 5 minutes
- Refresh tokens expire after 7 days
- Tokens are rotated on each refresh
- Logout blacklists all outstanding tokens for the user

## API Testing

### Get CSRF Token
```bash
GET /api/v1/auth/csrf/
```

### Login
```bash
POST /api/v1/auth/login/
Content-Type: application/json

{
  "email": "academic-admin@edustacked.test",
  "password": "admin@123"
}
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": 1,
    "email": "academic-admin@edustacked.test",
    "first_name": "Admin",
    "last_name": "User",
    "is_active": true
  }
}
```

### Refresh Token
```bash
POST /api/v1/auth/refresh/
Cookie: refresh_token=eyJ0eXAiOiJKV1QiLCJhbGc...
```

### Get Current User
```bash
GET /api/v1/auth/current-user/
Authorization: Bearer {access_token}
```

## Troubleshooting

### Login Fails with "Invalid email or password"

**Possible Causes:**
1. Wrong password - verify spelling
2. Test accounts haven't been created yet
3. Email doesn't exist in database
4. Account is inactive

**Solution:**
```bash
# Recreate test accounts
cd backend
python create_test_accounts.py
```

### Can't Access a School

**Possible Causes:**
1. User doesn't have membership in that school
2. School membership is inactive
3. School itself is inactive
4. User role doesn't have permission

**Solution:**
1. Check test credentials - each user is only in one or two schools
2. Use `academic-admin@edustacked.test` for North School access
3. Use `academic-outsider@edustacked.test` for South School access

### Token Expired

**Possible Causes:**
1. Access token is older than 5 minutes
2. Refresh token is older than 7 days
3. User logged out (tokens blacklisted)

**Solution:**
1. Refresh the token using the refresh endpoint
2. Or login again with credentials

## Development Tips

### Quick Django Shell Access
```bash
cd backend
python manage.py shell
```

Then in the shell:
```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='academic-admin@edustacked.test')
print(user.check_password('admin@123'))  # Should be True
```

### Reset Specific User Password
```bash
cd backend
python manage.py shell
```

Then:
```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='academic-admin@edustacked.test')
user.set_password('newpassword123')
user.save()
print("Password updated!")
```

### View All Test Data
```bash
cd backend
python check_users.py
```

## Next Steps

1. **Start the backend:**
   ```bash
   cd backend
   python manage.py runserver
   ```

2. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Login with test credentials:**
   - Email: `academic-admin@edustacked.test`
   - Password: `admin@123`

4. **Begin testing!**

---

**Last Updated:** October 2026  
**Test Data Version:** 1.0
