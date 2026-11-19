from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0002_remove_academicsession_academic_session_school_name_uniq_and_more"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromotionCriteria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("minimum_subjects_passed", models.PositiveSmallIntegerField(default=5)),
                ("pass_mark", models.DecimalField(decimal_places=2, default=Decimal("40.00"), max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("class_level", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="promotion_criteria", to="academics.classlevel")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="promotion_criteria", to="schools.school")),
            ],
            options={
                "ordering": ("class_level__name",),
                "constraints": [
                    models.CheckConstraint(condition=models.Q(minimum_subjects_passed__gte=1), name="promotion_criteria_min_subjects_positive"),
                    models.CheckConstraint(condition=models.Q(pass_mark__gte=0, pass_mark__lte=100), name="promotion_criteria_pass_mark_pct_range"),
                ],
            },
        ),
    ]
