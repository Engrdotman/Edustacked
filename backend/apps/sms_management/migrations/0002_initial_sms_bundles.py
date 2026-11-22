from datetime import date

from django.db import migrations
from django.utils import timezone


def seed_sms_data(apps, schema_editor):
    Bundle = apps.get_model("sms_management", "SMSBundle")
    Configuration = apps.get_model("sms_management", "SMSPlatformConfiguration")
    Allowance = apps.get_model("sms_management", "SMSMonthlyAllowance")
    School = apps.get_model("schools", "School")

    Configuration.objects.get_or_create(
        key="platform",
        defaults={"monthly_free_allowance": 50, "provider_cost_per_credit_minor": 600, "low_balance_threshold": 100},
    )
    for name, credits, price_minor, order in (
        ("Basic", 500, 375000, 1),
        ("Growth", 2000, 1400000, 2),
        ("Enterprise", 5000, 3250000, 3),
    ):
        Bundle.objects.get_or_create(name=name, defaults={
            "credits": credits, "price_minor": price_minor,
            "is_active": True, "display_order": order,
        })

    today = timezone.localdate()
    month_start = date(today.year, today.month, 1)
    for school_id in School.objects.filter(is_active=True).values_list("pk", flat=True).iterator():
        Allowance.objects.get_or_create(
            school_id=school_id, month_start=month_start,
            defaults={"allowance_credits": 50, "used_credits": 0},
        )


class Migration(migrations.Migration):
    dependencies = [("sms_management", "0001_initial")]

    operations = [migrations.RunPython(seed_sms_data, migrations.RunPython.noop)]
