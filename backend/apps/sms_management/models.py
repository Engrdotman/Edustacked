from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.schools.models import School


class SMSPlatformConfiguration(models.Model):
    """Platform-wide SMS pricing and allowance policy; provider secrets stay in env."""

    key = models.CharField(max_length=20, primary_key=True, default="platform", editable=False)
    monthly_free_allowance = models.PositiveSmallIntegerField(default=50)
    provider_cost_per_credit_minor = models.PositiveIntegerField(default=600, help_text="Configured Termii cost in kobo per SMS segment.")
    low_balance_threshold = models.PositiveIntegerField(default=100)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sms_configuration_updates")

    def clean(self):
        super().clean()
        if self.monthly_free_allowance > 10000:
            raise ValidationError({"monthly_free_allowance": "Monthly free allowance cannot exceed 10,000 credits."})
        if self.provider_cost_per_credit_minor <= 0:
            raise ValidationError({"provider_cost_per_credit_minor": "Provider cost must be greater than zero."})


class SMSBundle(models.Model):
    name = models.CharField(max_length=80, unique=True)
    credits = models.PositiveIntegerField()
    price_minor = models.PositiveBigIntegerField(help_text="Price in kobo.")
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "credits", "id")
        constraints = [
            models.CheckConstraint(condition=Q(credits__gt=0), name="sms_bundle_positive_credits"),
            models.CheckConstraint(condition=Q(price_minor__gt=0), name="sms_bundle_positive_price"),
        ]


class SMSWallet(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="sms_wallet")
    purchased_balance = models.PositiveBigIntegerField(default=0)
    paid_value_balance_minor = models.PositiveBigIntegerField(default=0, help_text="Unrecognized bundle revenue value remaining in the wallet.")
    sending_suspended = models.BooleanField(default=False)
    suspension_reason = models.CharField(max_length=500, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SMSMonthlyAllowance(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sms_monthly_allowances")
    month_start = models.DateField()
    allowance_credits = models.PositiveIntegerField(default=50)
    used_credits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-month_start",)
        constraints = [
            models.UniqueConstraint(fields=("school", "month_start"), name="sms_monthly_school_period_uniq"),
            models.CheckConstraint(condition=Q(used_credits__lte=models.F("allowance_credits")), name="sms_monthly_usage_within_allowance"),
        ]
        indexes = [models.Index(fields=("month_start", "school"), name="sms_monthly_period_idx")]


class SMSPurchase(models.Model):
    class Provider(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"
        FLUTTERWAVE = "flutterwave", "Flutterwave"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="sms_purchases")
    bundle = models.ForeignKey(SMSBundle, null=True, blank=True, on_delete=models.PROTECT, related_name="purchases")
    bundle_name = models.CharField(max_length=80)
    credits = models.PositiveIntegerField()
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    reference = models.CharField(max_length=100, unique=True)
    provider_transaction_id = models.CharField(max_length=120, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    customer_email = models.EmailField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sms_purchases_created")
    provider_metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("school", "status", "created_at"), name="sms_purchase_school_idx")]
        constraints = [models.CheckConstraint(condition=Q(credits__gt=0) & Q(amount_minor__gt=0), name="sms_purchase_positive_amount")]


class SMSMessageBatch(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        SUBMITTED = "submitted", "Submitted"
        PARTIAL = "partial", "Partially submitted"
        FAILED = "failed", "Failed"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="sms_batches")
    idempotency_key = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    recipient_count = models.PositiveSmallIntegerField()
    total_segments = models.PositiveIntegerField()
    free_credits = models.PositiveIntegerField(default=0)
    paid_credits = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="sms_batches_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("school", "idempotency_key"), name="sms_school_idempotency_uniq")]
        indexes = [models.Index(fields=("school", "created_at"), name="sms_batch_school_date_idx")]


class SMSMessageLog(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SUBMITTED = "submitted", "Submitted"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Delivery status unknown"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="sms_messages")
    batch = models.ForeignKey(SMSMessageBatch, on_delete=models.PROTECT, related_name="messages")
    phone = models.CharField(max_length=20)
    message = models.TextField()
    segments = models.PositiveSmallIntegerField()
    free_credits = models.PositiveSmallIntegerField(default=0)
    paid_credits = models.PositiveSmallIntegerField(default=0)
    paid_sales_value_minor = models.PositiveBigIntegerField(default=0)
    provider_cost_estimate_minor = models.PositiveBigIntegerField(default=0)
    paid_provider_cost_estimate_minor = models.PositiveBigIntegerField(default=0)
    actual_provider_cost_minor = models.PositiveBigIntegerField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("school", "provider_message_id"), condition=~Q(provider_message_id=""), name="sms_school_provider_msg_uniq"),
        ]
        indexes = [
            models.Index(fields=("school", "status", "created_at"), name="sms_message_school_idx"),
            models.Index(fields=("provider_message_id",), name="sms_message_provider_idx"),
        ]


class SMSWalletTransaction(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Verified purchase"
        CONSUMPTION = "consumption", "SMS sent"
        REFUND = "refund", "Failed delivery refund"
        ADJUSTMENT = "adjustment", "Platform adjustment"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="sms_wallet_transactions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    credits = models.IntegerField(help_text="Signed credit movement.")
    description = models.CharField(max_length=240)
    reference_key = models.CharField(max_length=160, unique=True)
    purchase = models.ForeignKey(SMSPurchase, null=True, blank=True, on_delete=models.PROTECT, related_name="wallet_transactions")
    message = models.ForeignKey(SMSMessageLog, null=True, blank=True, on_delete=models.PROTECT, related_name="wallet_transactions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="sms_wallet_transactions")
    unit_sale_price_minor = models.PositiveIntegerField(default=0)
    provider_cost_per_credit_minor = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.CheckConstraint(condition=~Q(credits=0), name="sms_wallet_tx_nonzero")]
        indexes = [models.Index(fields=("school", "created_at"), name="sms_wallet_tx_school_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("SMS wallet transactions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("SMS wallet transactions cannot be deleted.")


class SMSProviderEvent(models.Model):
    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=160)
    payment = models.ForeignKey(SMSPurchase, null=True, blank=True, on_delete=models.PROTECT, related_name="provider_events")
    message = models.ForeignKey(SMSMessageLog, null=True, blank=True, on_delete=models.PROTECT, related_name="provider_events")
    event_type = models.CharField(max_length=80, blank=True)
    payload_hash = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "event_id"), name="sms_provider_event_uniq")]
        indexes = [models.Index(fields=("provider", "received_at"), name="sms_provider_event_date_idx")]
