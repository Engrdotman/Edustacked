from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from offline_exam.models import LocalStudentCredential


class Command(BaseCommand):
    help = "Create a local student login. This does not create or modify the central SMS student."

    def add_arguments(self, parser):
        parser.add_argument("--central-student-id", type=int, required=True)
        parser.add_argument("--admission-number", required=True)
        parser.add_argument("--name", required=True)

    def handle(self, *args, **options):
        password = getpass("Temporary local examination password (12+ chars): ")
        confirmation = getpass("Confirm password: ")
        if len(password) < 12 or password != confirmation:
            raise CommandError("Passwords must match and be at least 12 characters long.")
        credential = LocalStudentCredential(
            central_student_id=options["central_student_id"],
            admission_number=options["admission_number"].strip(),
            display_name=options["name"].strip(),
        )
        credential.set_password(password)
        try:
            credential.save()
        except Exception as exc:
            raise CommandError(f"Student local account was not created: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Created local exam login for {credential.admission_number}. Deliver the temporary password through the school's approved private channel."))
