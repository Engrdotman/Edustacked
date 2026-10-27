from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class School(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=~Q(name=""), name="school_name_not_blank"),
            models.CheckConstraint(condition=~Q(slug=""), name="school_slug_not_blank"),
        ]

    def clean(self):
        super().clean()
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        if self.slug:
            self.slug = slugify(self.slug)
        if not self.slug:
            raise ValidationError({"slug": "A school slug is required."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SchoolMembership(models.Model):
    class Role(models.TextChoices):
        SCHOOL_ADMIN = "school_admin", "School admin"
        SCHOOL_MANAGER = "school_manager", "School manager"
        TEACHER = "teacher", "Teacher"
        ACCOUNTANT = "accountant", "Accountant"
        RECEPTIONIST = "receptionist", "Receptionist / front desk"
        MEMBER = "member", "Legacy member (no permissions)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_memberships",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school"], name="unique_user_school_membership"
            ),
            models.CheckConstraint(
                condition=Q(
                    role__in=(
                        "school_admin",
                        "school_manager",
                        "teacher",
                        "accountant",
                        "receptionist",
                        "member",
                    )
                ),
                name="school_membership_valid_role",
            ),
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def clean(self):
        super().clean()
        if self.role not in self.Role.values:
            raise ValidationError({"role": "Select a valid school membership role."})

    def __str__(self):
        return f"{self.user} — {self.school} ({self.role})"
