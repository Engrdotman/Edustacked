from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def initialize_onboarding_progress(apps, schema_editor):
    School = apps.get_model("schools", "School")
    Progress = apps.get_model("schools", "SchoolOnboardingProgress")
    alias = schema_editor.connection.alias
    Progress.objects.using(alias).bulk_create(
        [Progress(school_id=school_id) for school_id in School.objects.using(alias).values_list("id", flat=True)],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0007_school_description_school_local_government_area_and_more"),
        ("accounts", "0003_hybrid_school_onboarding"),
    ]

    operations = [
        migrations.AddField(model_name="school", name="country", field=models.CharField(default="Nigeria", max_length=100)),
        migrations.AddField(model_name="school", name="school_type", field=models.CharField(choices=[("primary", "Primary"), ("secondary", "Secondary"), ("both", "Primary and secondary")], default="both", max_length=12)),
        migrations.AddField(model_name="school", name="registration_key", field=models.CharField(blank=True, max_length=64, null=True, unique=True)),
        migrations.AddField(model_name="school", name="verification_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="school", name="verified_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="school", name="verification_status", field=models.CharField(choices=[("pending_verification", "Pending verification"), ("under_review", "Under review"), ("verified", "Verified"), ("rejected", "Rejected"), ("suspended", "Suspended")], default="verified", max_length=24)),
        migrations.AlterField(model_name="school", name="verification_status", field=models.CharField(choices=[("pending_verification", "Pending verification"), ("under_review", "Under review"), ("verified", "Verified"), ("rejected", "Rejected"), ("suspended", "Suspended")], default="pending_verification", max_length=24)),
        migrations.RemoveConstraint(model_name="schoolmembership", name="school_membership_valid_role"),
        migrations.AlterField(model_name="schoolmembership", name="role", field=models.CharField(choices=[("school_owner", "School owner"), ("principal", "Principal"), ("school_admin", "School admin"), ("school_manager", "School manager"), ("teacher", "Teacher"), ("accountant", "Accountant"), ("receptionist", "Receptionist / front desk"), ("member", "Legacy member (no permissions)")], default="member", max_length=20)),
        migrations.AddConstraint(model_name="schoolmembership", constraint=models.CheckConstraint(condition=models.Q(("role__in", ("school_admin", "school_owner", "principal", "school_manager", "teacher", "accountant", "receptionist", "member"))), name="school_membership_valid_role")),
        migrations.AddConstraint(model_name="schoolmembership", constraint=models.UniqueConstraint(condition=models.Q(("role", "school_owner")), fields=("school",), name="school_single_owner_uniq")),
        migrations.CreateModel(
            name="SchoolOnboardingProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("current_step", models.PositiveSmallIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="onboarding_progress", to="schools.school")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="school_onboarding_updates", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SchoolVerificationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=32)),
                ("from_status", models.CharField(blank=True, max_length=24)),
                ("to_status", models.CharField(blank=True, max_length=24)),
                ("reason", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="school_verification_events", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="verification_events", to="schools.school")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddIndex(model_name="schoolverificationevent", index=models.Index(fields=["school", "created_at"], name="school_verify_event_idx")),
        migrations.RunPython(initialize_onboarding_progress, migrations.RunPython.noop),
    ]
