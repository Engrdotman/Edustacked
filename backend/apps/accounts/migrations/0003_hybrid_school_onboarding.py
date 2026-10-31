import uuid
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_alter_user_options_user_created_at_user_login_email_and_more")]

    operations = [
        migrations.AddField(model_name="user", name="phone_number", field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name="user", name="email_verified_at", field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
        migrations.AddField(model_name="user", name="phone_verified_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name="EmailVerificationToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selector", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("token_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_verification_tokens", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(model_name="emailverificationtoken", index=models.Index(fields=["user", "expires_at"], name="acct_verify_user_exp_idx")),
        migrations.CreateModel(
            name="DemoRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("administrator_name", models.CharField(max_length=150)),
                ("school_name", models.CharField(max_length=200)),
                ("email", models.EmailField(max_length=254)),
                ("phone_number", models.CharField(max_length=30)),
                ("message", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("new", "New"), ("contacted", "Contacted"), ("closed", "Closed")], default="new", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
