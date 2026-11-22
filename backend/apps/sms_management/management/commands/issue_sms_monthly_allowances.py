from django.core.management.base import BaseCommand

from apps.sms_management.services import issue_monthly_allowances


class Command(BaseCommand):
    help = "Idempotently issue this calendar month's free SMS allowance to active schools."

    def handle(self, *args, **options):
        result = issue_monthly_allowances()
        self.stdout.write(self.style.SUCCESS(
            f"SMS allowance period {result['month_start']}: "
            f"created {result['created']} allowance(s) for {result['schools']} active school(s)."
        ))
