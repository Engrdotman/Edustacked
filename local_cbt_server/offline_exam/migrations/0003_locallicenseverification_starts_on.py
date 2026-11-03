from datetime import date

from django.db import migrations, models


def populate_license_start_dates(apps, schema_editor):
    Verification = apps.get_model("offline_exam", "LocalLicenseVerification")
    ImportedExamination = apps.get_model("offline_exam", "ImportedExamination")
    for row in Verification.objects.all().iterator():
        starts_on = None
        packages = ImportedExamination.objects.filter(school_id=row.school_id).values_list("config", flat=True)
        for config in packages:
            license_payload = (config.get("license") or {}).get("payload") or {}
            if license_payload.get("license_id") == str(row.license_id):
                try:
                    starts_on = date.fromisoformat(license_payload["starts_on"])
                except (KeyError, TypeError, ValueError):
                    starts_on = None
                break
        row.starts_on = starts_on or date.min
        row.save(update_fields=("starts_on",))


class Migration(migrations.Migration):
    dependencies = [("offline_exam", "0002_localbackuprecord")]

    operations = [
        migrations.AddField(
            model_name="locallicenseverification",
            name="starts_on",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(populate_license_start_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="locallicenseverification",
            name="starts_on",
            field=models.DateField(),
        ),
    ]
