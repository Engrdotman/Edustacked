from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from pathlib import Path
from uuid import uuid4
import uuid


MAX_SCHOOL_LOGO_SIZE = 2 * 1024 * 1024


def validate_school_logo_size(value):
    if value.size > MAX_SCHOOL_LOGO_SIZE:
        raise ValidationError("School logos must be 2 MB or smaller.")


def school_logo_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"school-logos/{instance.pk}/{uuid4().hex}{extension}"


class School(models.Model):
    class SchoolType(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        BOTH = "both", "Primary and secondary"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending_verification", "Pending verification"
        UNDER_REVIEW = "under_review", "Under review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(
        upload_to=school_logo_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_school_logo_size],
    )
    state = models.CharField(max_length=100, blank=True)
    local_government_area = models.CharField(max_length=120, blank=True)
    website = models.URLField(max_length=255, blank=True)
    motto = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    school_type = models.CharField(max_length=12, choices=SchoolType.choices, default=SchoolType.BOTH)
    country = models.CharField(max_length=100, default="Nigeria")
    registration_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    verification_status = models.CharField(max_length=24, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    verification_reason = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
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


def default_contact_preferences():
    return {"email": True, "phone": True}


class SchoolSettings(models.Model):
    DATE_FORMATS = (
        ("DD/MM/YYYY", "DD/MM/YYYY"),
        ("MM/DD/YYYY", "MM/DD/YYYY"),
        ("YYYY-MM-DD", "YYYY-MM-DD"),
    )

    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="settings")
    default_currency = models.CharField(max_length=3, default="NGN")
    time_zone = models.CharField(max_length=64, default="Africa/Lagos")
    date_format = models.CharField(max_length=10, choices=DATE_FORMATS, default="DD/MM/YYYY")
    academic_year_label = models.CharField(max_length=80, default="Academic year")
    contact_preferences = models.JSONField(default=default_contact_preferences)
    branding_primary_color = models.CharField(max_length=7, default="#285744")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(default_currency__regex=r"^[A-Z]{3}$"),
                name="school_settings_currency_code_format",
            ),
            models.CheckConstraint(
                condition=Q(branding_primary_color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="school_settings_brand_color_format",
            ),
        ]

    def __str__(self):
        return f"Settings for {self.school}"


class SchoolMembership(models.Model):
    class Role(models.TextChoices):
        SCHOOL_OWNER = "school_owner", "School owner"
        PRINCIPAL = "principal", "Principal"
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
                        "school_owner",
                        "principal",
                        "school_manager",
                        "teacher",
                        "accountant",
                        "receptionist",
                        "member",
                    )
                ),
                name="school_membership_valid_role",
            ),
            models.UniqueConstraint(fields=("school",), condition=Q(role="school_owner"), name="school_single_owner_uniq"),
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def clean(self):
        super().clean()
        if self.role not in self.Role.values:
            raise ValidationError({"role": "Select a valid school membership role."})

    def __str__(self):
        return f"{self.user} — {self.school} ({self.role})"


class SchoolOnboardingProgress(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="onboarding_progress")
    current_step = models.PositiveSmallIntegerField(default=1)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="school_onboarding_updates")
    updated_at = models.DateTimeField(auto_now=True)


class SchoolVerificationEvent(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="verification_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="school_verification_events")
    action = models.CharField(max_length=32)
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("school", "created_at"), name="school_verify_event_idx")]
