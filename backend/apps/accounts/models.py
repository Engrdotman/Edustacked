from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


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
