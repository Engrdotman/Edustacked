from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
import uuid


class User(AbstractUser):
    """Custom account with a separately constrained, email-based login identity."""

    login_email = models.EmailField(
        max_length=254,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)
    phone_number = models.CharField(max_length=30, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("login_email"),
                condition=Q(login_email__isnull=False),
                name="accounts_login_email_ci_unique",
            )
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "email" in update_fields or "login_email" in update_fields:
            normalized_email = self.email.strip().lower() if self.email else ""
            self.email = normalized_email
            self.login_email = normalized_email or None
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {
                    "email",
                    "login_email",
                    "updated_at",
                }
        elif update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        super().save(*args, **kwargs)


class EmailVerificationToken(models.Model):
    """Store only a digest of the one-time email verification secret."""

    selector = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_verification_tokens")
    token_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("user", "expires_at"), name="acct_verify_user_exp_idx")]


class DemoRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CLOSED = "closed", "Closed"

    administrator_name = models.CharField(max_length=150)
    school_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone_number = models.CharField(max_length=30)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
