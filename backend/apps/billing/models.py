from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.schools.models import School


class CreditAccount(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="credit_account")
    balance = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class CreditPackage(models.Model):
    name = models.CharField(max_length=100, unique=True)
    credits = models.PositiveIntegerField()
    price_minor = models.PositiveBigIntegerField(help_text="Price in kobo (NGN subunit).")
    description = models.CharField(max_length=240, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "price_minor", "id")
        constraints = [
            models.CheckConstraint(condition=Q(credits__gt=0), name="credit_package_positive_credits"),
            models.CheckConstraint(condition=Q(price_minor__gt=0), name="credit_package_positive_price"),
        ]

    def __str__(self):
        return f"{self.name} ({self.credits} credits)"


class CreditPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed / under review"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="credit_payments")
    package = models.ForeignKey(CreditPackage, null=True, on_delete=models.PROTECT, related_name="payments")
    package_name = models.CharField(max_length=100)
    credits = models.PositiveIntegerField()
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    provider = models.CharField(max_length=30, default="paystack")
    reference = models.CharField(max_length=100, unique=True)
    provider_transaction_id = models.CharField(max_length=100, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    customer_email = models.EmailField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_payments_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    provider_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("school", "status", "created_at"), name="billing_payment_school_idx")]


class ReportCardBilling(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="report_card_billings")
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="report_card_billings")
    academic_session = models.ForeignKey("academics.AcademicSession", on_delete=models.PROTECT, related_name="report_card_billings")
    term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="report_card_billings")
    report_card = models.ForeignKey("report_cards.ReportCard", on_delete=models.PROTECT, related_name="billing_records")
    revision = models.ForeignKey("report_cards.ReportCardRevision", on_delete=models.PROTECT, related_name="billing_records")
    charged_at = models.DateTimeField(null=True, blank=True)
    legacy_waived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("school", "student", "academic_session", "term"), name="report_card_billing_period_uniq")]
        indexes = [models.Index(fields=("school", "academic_session", "term"), name="billing_report_period_idx")]


class CreditTransaction(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Verified purchase"
        REPORT_CARD = "report_card", "Report-card finalization"
        ADJUSTMENT = "adjustment", "Platform adjustment"
        REVERSAL = "reversal", "Payment reversal"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="credit_transactions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.IntegerField(help_text="Signed credit movement.")
    description = models.CharField(max_length=240)
    payment = models.ForeignKey(CreditPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_transactions")
    report_card_billing = models.ForeignKey(ReportCardBilling, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_transactions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_transactions")
    reference_key = models.CharField(max_length=140, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.CheckConstraint(condition=~Q(amount=0), name="credit_transaction_nonzero")]
        indexes = [models.Index(fields=("school", "created_at"), name="billing_ledger_school_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Credit ledger entries are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Credit ledger entries cannot be deleted.")


class ReconciliationIssue(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="billing_issues")
    payment = models.ForeignKey(CreditPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="reconciliation_issues")
    kind = models.CharField(max_length=40)
    description = models.CharField(max_length=500)
    provider_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="billing_issues_resolved")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("kind", "provider_reference"), condition=~Q(provider_reference=""), name="billing_issue_provider_ref_uniq")]
