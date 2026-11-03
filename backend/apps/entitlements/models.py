from datetime import date as calendar_date, timedelta
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.schools.models import School


class ServicePlan(models.Model):
    """A separately priced add-on product; independent of report-card credits."""

    service_code = models.SlugField(max_length=50)
    name = models.CharField(max_length=120)
    package_type = models.CharField(max_length=50)
    student_capacity = models.PositiveIntegerField()
    duration_days = models.PositiveSmallIntegerField(default=365)
    price_minor = models.PositiveBigIntegerField(help_text="Price in kobo for NGN plans.")
    currency = models.CharField(max_length=3, default="NGN")
    description = models.CharField(max_length=240, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("service_code", "price_minor", "id")
        constraints = [
            models.UniqueConstraint(fields=("service_code", "package_type"), name="service_plan_code_package_uniq"),
            models.CheckConstraint(condition=Q(student_capacity__gt=0), name="service_plan_capacity_positive"),
            models.CheckConstraint(condition=Q(duration_days__gt=0), name="service_plan_duration_positive"),
            models.CheckConstraint(condition=Q(price_minor__gt=0), name="service_plan_price_positive"),
        ]

    def __str__(self):
        return f"{self.name} ({self.service_code})"


class ServiceEntitlement(models.Model):
    """Auditable, school-scoped access grant for one separately licensed service."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    license_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="service_entitlements")
    service_code = models.SlugField(max_length=50)
    plan = models.ForeignKey(ServicePlan, null=True, blank=True, on_delete=models.PROTECT, related_name="entitlements")
    package_type = models.CharField(max_length=50)
    student_capacity = models.PositiveIntegerField()
    starts_on = models.DateField()
    expires_on = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    payment_reference = models.CharField(max_length=100, blank=True)
    offline_grace_days = models.PositiveSmallIntegerField(default=settings.CBT_OFFLINE_GRACE_DAYS)
    signed_license = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="service_entitlements_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("school", "service_code", "status"), name="entitlement_school_service_idx"),
            models.Index(fields=("service_code", "expires_on"), name="entitlement_service_expiry_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(student_capacity__gt=0), name="service_entitlement_capacity_positive"),
            models.CheckConstraint(condition=Q(expires_on__gte=models.F("starts_on")), name="service_entitlement_dates_ordered"),
            models.UniqueConstraint(fields=("payment_reference",), condition=~Q(payment_reference=""), name="service_entitlement_payment_ref_uniq"),
        ]

    def clean(self):
        super().clean()
        if self.expires_on and self.starts_on and self.expires_on < self.starts_on:
            raise ValidationError({"expires_on": "Expiry date must be on or after the start date."})
        if self.plan_id and self.plan.service_code != self.service_code:
            raise ValidationError({"plan": "The selected plan belongs to another service."})

    def license_payload(self):
        return {
            "license_id": str(self.license_id),
            "school_id": self.school_id,
            "service_code": self.service_code,
            "package_type": self.package_type,
            "student_capacity": self.student_capacity,
            "starts_on": self.starts_on.isoformat(),
            "expires_on": self.expires_on.isoformat(),
            "offline_grace_days": self.offline_grace_days,
        }

    def save(self, *args, **kwargs):
        self.signed_license = signing.dumps(
            self.license_payload(),
            key=settings.CBT_LICENSE_SIGNING_KEY,
            salt="edustacked.service-license.v1",
            compress=True,
        )
        return super().save(*args, **kwargs)

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.starts_on <= today <= self.expires_on

    def __str__(self):
        return f"{self.school} — {self.service_code} ({self.status})"


def verify_offline_license(token, *, today=None):
    """Verify an issued license without network access and apply its grace period."""
    payload = signing.loads(token, key=settings.CBT_LICENSE_SIGNING_KEY, salt="edustacked.service-license.v1")
    today = today or timezone.localdate()
    starts_on = calendar_date.fromisoformat(payload["starts_on"])
    expires_on = calendar_date.fromisoformat(payload["expires_on"])
    allowed_through = expires_on + timedelta(days=int(payload["offline_grace_days"]))
    payload["valid_for_offline_use"] = starts_on <= today <= allowed_through
    payload["grace_period"] = today > expires_on and today <= allowed_through
    return payload
