import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.schools.models import School, SchoolMembership


DEMO_SCHOOLS = (
    ("edustacked-test-north", "EDUstacked Test School North"),
    ("edustacked-test-south", "EDUstacked Test School South"),
)

ACCOUNTS = (
    ("academic-admin@edustacked.test", "Academic", "Admin", SchoolMembership.Role.SCHOOL_ADMIN, 0),
    ("academic-manager@edustacked.test", "Academic", "Manager", SchoolMembership.Role.SCHOOL_MANAGER, 0),
    ("academic-teacher@edustacked.test", "Academic", "Teacher", SchoolMembership.Role.TEACHER, 0),
    ("academic-outsider@edustacked.test", "Other School", "Admin", SchoolMembership.Role.SCHOOL_ADMIN, 1),
    ("academic-receptionist@edustacked.test", "Academic", "Receptionist", SchoolMembership.Role.RECEPTIONIST, 0),
    ("academic-accountant@edustacked.test", "Academic", "Accountant", SchoolMembership.Role.ACCOUNTANT, 0),
)


class Command(BaseCommand):
    help = "Create local-only EDUstacked academic and student setup accounts for manual acceptance testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Generate and set new passwords for all existing demo accounts.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Test accounts can only be seeded when DEBUG=True.")
        if not settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"):
            raise CommandError("Test accounts can only be seeded into the local SQLite development database.")

        User = get_user_model()
        generated_passwords = {}
        try:
            with transaction.atomic():
                schools = [
                    School.objects.get_or_create(slug=slug, defaults={"name": name})[0]
                    for slug, name in DEMO_SCHOOLS
                ]
                for school in schools:
                    if not school.is_active:
                        raise CommandError(f"Demo school {school.slug} is inactive; activate it before seeding accounts.")

                for email, first_name, last_name, role, school_index in ACCOUNTS:
                    user = User.objects.filter(login_email=email).first()
                    if user is None and User.objects.filter(email__iexact=email).exists():
                        raise CommandError(
                            f"{email} belongs to a legacy account. Resolve it before using the demo account command."
                        )
                    new_password = user is None or options["reset_passwords"]
                    password = secrets.token_urlsafe(24) if new_password else None
                    if user is None:
                        user = User.objects.create_user(
                            username=email,
                            email=email,
                            password=password,
                            first_name=first_name,
                            last_name=last_name,
                        )
                    else:
                        if not user.is_active:
                            raise CommandError(f"Demo account {email} is inactive; review it before seeding.")
                        if new_password:
                            user.set_password(password)
                            user.save(update_fields=("password", "updated_at"))

                    membership, _ = SchoolMembership.objects.get_or_create(
                        user=user,
                        school=schools[school_index],
                        defaults={"role": role, "is_active": True},
                    )
                    if membership.role != role or not membership.is_active:
                        membership.role = role
                        membership.is_active = True
                        membership.save(update_fields=("role", "is_active"))
                    if new_password:
                        generated_passwords[email] = password
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Could not seed academic test accounts: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Academic and student test schools and accounts are ready (local SQLite only)."))
        for slug, name in DEMO_SCHOOLS:
            self.stdout.write(f"School: {name} [{slug}]")
        for email, _, _, role, school_index in ACCOUNTS:
            password = generated_passwords.get(email)
            if password:
                self.stdout.write(f"{role}: {email}  password: {password}")
            else:
                self.stdout.write(f"{role}: {email}  password unchanged (use the password from its first seed/reset run)")
        self.stdout.write(self.style.WARNING("These are development test credentials. Do not use them outside local development."))
