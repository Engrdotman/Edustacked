from django.db import migrations


PACKAGES = (
    {
        "name": "Starter — 100 credits",
        "credits": 100,
        "price_minor": 3_000_000,
        "description": "₦300 per credit. Suitable for a smaller report-card run.",
        "display_order": 1,
    },
    {
        "name": "Growth — 300 credits",
        "credits": 300,
        "price_minor": 4_500_000,
        "description": "₦150 per credit. A lower unit rate for growing schools.",
        "display_order": 2,
    },
    {
        "name": "School — 500 credits",
        "credits": 500,
        "price_minor": 5_000_000,
        "description": "₦100 per credit. Best value for larger report-card runs.",
        "display_order": 3,
    },
)


def seed_packages(apps, schema_editor):
    CreditPackage = apps.get_model("billing", "CreditPackage")
    database = schema_editor.connection.alias
    package_names = [package["name"] for package in PACKAGES]

    # Keep any existing package/payment records for history, but show only the
    # three school-approved packages to new buyers.
    CreditPackage.objects.using(database).exclude(name__in=package_names).filter(
        is_active=True
    ).update(is_active=False)

    for package in PACKAGES:
        CreditPackage.objects.using(database).update_or_create(
            name=package["name"],
            defaults={**package, "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_grandfather_existing_finalized_cards")]

    operations = [migrations.RunPython(seed_packages, migrations.RunPython.noop)]
