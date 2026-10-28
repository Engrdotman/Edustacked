#!/usr/bin/env python
"""
Create test user accounts for development and testing.

This script creates test user accounts with known credentials for manual testing
and QA. All test accounts use test passwords and the domain @edustacked.test.

Usage:
    python manage.py shell < create_test_accounts.py
    
Or directly:
    python create_test_accounts.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.schools.models import School, SchoolMembership

User = get_user_model()

# Test account definitions
TEST_ACCOUNTS = [
    {
        "email": "academic-admin@edustacked.test",
        "password": "admin@123",
        "first_name": "Admin",
        "last_name": "User",
        "role": "school_admin",
        "school": "EDUstacked Test School North",
    },
    {
        "email": "academic-manager@edustacked.test",
        "password": "manager@123",
        "first_name": "Manager",
        "last_name": "User",
        "role": "school_manager",
        "school": "EDUstacked Test School North",
    },
    {
        "email": "academic-teacher@edustacked.test",
        "password": "teacher@123",
        "first_name": "Teacher",
        "last_name": "User",
        "role": "teacher",
        "school": "EDUstacked Test School North",
    },
    {
        "email": "academic-receptionist@edustacked.test",
        "password": "receptionist@123",
        "first_name": "Receptionist",
        "last_name": "User",
        "role": "receptionist",
        "school": "EDUstacked Test School North",
    },
    {
        "email": "academic-accountant@edustacked.test",
        "password": "accountant@123",
        "first_name": "Accountant",
        "last_name": "User",
        "role": "accountant",
        "school": "EDUstacked Test School North",
    },
    {
        "email": "academic-outsider@edustacked.test",
        "password": "outsider@123",
        "first_name": "Outside",
        "last_name": "User",
        "role": "school_admin",
        "school": "EDUstacked Test School South",
    },
]

print("=" * 70)
print("CREATING TEST USER ACCOUNTS")
print("=" * 70)

created_count = 0
updated_count = 0

for account in TEST_ACCOUNTS:
    email = account["email"]
    password = account["password"]
    
    # Get or create school
    try:
        school = School.objects.get(name=account["school"])
    except School.DoesNotExist:
        print(f"\n⚠️  School not found: {account['school']}")
        print(f"    Creating school...")
        school = School.objects.create(
            name=account["school"],
            slug=account["school"].lower().replace(" ", "-"),
        )
    
    # Get or create user
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": account["first_name"],
            "last_name": account["last_name"],
            "is_active": True,
        }
    )
    
    # Update password (always, in case it was wrong)
    user.set_password(password)
    user.save()
    
    # Get or create membership
    membership, membership_created = SchoolMembership.objects.get_or_create(
        user=user,
        school=school,
        defaults={"role": account["role"], "is_active": True}
    )
    
    status = "✓ CREATED" if created else "⚠  UPDATED "
    symbol = "🆕" if created else "🔄"
    
    print(f"\n{symbol} {status}: {email}")
    print(f"   Password: {password}")
    print(f"   School: {school.name} ({account['role']})")
    
    if created:
        created_count += 1
    else:
        updated_count += 1

print("\n" + "=" * 70)
print(f"✓ COMPLETE: Created {created_count} | Updated {updated_count} accounts")
print("=" * 70)
print("\n📝 TEST CREDENTIALS:")
print("-" * 70)
for account in TEST_ACCOUNTS:
    print(f"  Email:    {account['email']}")
    print(f"  Password: {account['password']}")
    print()

print("🚀 You can now login with these credentials!")
print("-" * 70)
