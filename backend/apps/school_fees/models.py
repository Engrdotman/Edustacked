from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.models import School
from apps.students.models import Guardian, Student, StudentEnrollment


class SchoolFeeSettings(models.Model):
    class Provider(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"
        FLUTTERWAVE = "flutterwave", "Flutterwave"
        BACHS = "bachs", "Bachs"

    class AccountStatus(models.TextChoices):
        NOT_CONFIGURED = "not_configured", "Not configured"
        PENDING = "pending", "Pending verification"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Verification failed"

    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="fee_payment_settings")
    bank_name = models.CharField(max_length=120, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=200, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_type = models.CharField(max_length=20, blank=True)
    account_status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.NOT_CONFIGURED)
    account_verified_name = models.CharField(max_length=200, blank=True)
    account_verified_at = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=20, choices=Provider.choices, blank=True)
    provider_account_id = models.CharField(max_length=100, blank=True)
    online_enabled = models.BooleanField(default=False)
    allow_excess_credit = models.BooleanField(default=True)
    allowed_channels = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.online_enabled and (self.account_status != self.AccountStatus.VERIFIED or not self.provider_account_id):
            raise ValidationError({"online_enabled": "Verify a receiving account and connect a payment provider before enabling online collections."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def masked_account_number(self):
        if not self.account_number:
            return ""
        return f"{'•' * max(4, len(self.account_number) - 4)}{self.account_number[-4:]}"


class FeeSchedule(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="fee_schedules")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="fee_schedules")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fee_schedules")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="fee_schedules")
    class_arm = models.ForeignKey(ClassArm, null=True, blank=True, on_delete=models.PROTECT, related_name="fee_schedules")
    category = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    amount_minor = models.PositiveBigIntegerField(help_text="Fee amount in kobo.")
    currency = models.CharField(max_length=3, default="NGN")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="school_fee_schedules_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("academic_session__start_date", "term__sequence", "class_level__name", "category", "id")
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="fee_schedule_positive_amount"),
            models.UniqueConstraint(fields=("school", "academic_session", "term", "class_level", "class_arm", "category"), condition=Q(class_arm__isnull=False), name="fee_schedule_arm_category_uniq"),
            models.UniqueConstraint(fields=("school", "academic_session", "term", "class_level", "category"), condition=Q(class_arm__isnull=True), name="fee_schedule_class_category_uniq"),
        ]
        indexes = [models.Index(fields=("school", "academic_session", "term", "status"), name="fee_schedule_school_idx")]

    def clean(self):
        super().clean()
        if self.academic_session_id and self.academic_session.school_id != self.school_id:
            raise ValidationError({"academic_session": "Select a session from this school."})
        if self.term_id and (self.term.school_id != self.school_id or self.term.academic_session_id != self.academic_session_id):
            raise ValidationError({"term": "Select a term from the selected school and session."})
        if self.class_level_id and self.class_level.school_id != self.school_id:
            raise ValidationError({"class_level": "Select a class from this school."})
        if self.class_arm_id and (self.class_arm.school_id != self.school_id or self.class_arm.class_level_id != self.class_level_id):
            raise ValidationError({"class_arm": "Select an arm within the selected class."})
        if self.due_date and self.term_id and (self.due_date < self.term.start_date or self.due_date > self.term.end_date):
            raise ValidationError({"due_date": "The due date must fall within the selected term."})
        self.category = self.category.strip()
        if not self.category:
            raise ValidationError({"category": "Enter a fee category such as Tuition or Uniform."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category} · {self.class_level} · {self.term}"


class FeeCharge(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_charges")
    fee_schedule = models.ForeignKey(FeeSchedule, on_delete=models.PROTECT, related_name="charges")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_charges")
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="fee_charges")
    amount_minor = models.PositiveBigIntegerField(help_text="Snapshot of the fee when it was issued.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fee_charges_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("student__last_name", "student__first_name", "fee_schedule__category")
        constraints = [
            models.UniqueConstraint(fields=("fee_schedule", "student"), name="fee_charge_schedule_student_uniq"),
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="fee_charge_positive_amount"),
        ]
        indexes = [models.Index(fields=("school", "student", "created_at"), name="fee_charge_student_idx")]

    def clean(self):
        super().clean()
        if self.fee_schedule_id and self.fee_schedule.school_id != self.school_id:
            raise ValidationError({"fee_schedule": "The fee schedule belongs to another school."})
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({"student": "The student belongs to another school."})
        if self.enrollment_id and (self.enrollment.school_id != self.school_id or self.enrollment.student_id != self.student_id):
            raise ValidationError({"enrollment": "The enrollment does not belong to this student and school."})
        if self.fee_schedule_id and self.enrollment_id and (
            self.enrollment.academic_session_id != self.fee_schedule.academic_session_id
            or self.enrollment.class_level_id != self.fee_schedule.class_level_id
            or (self.fee_schedule.class_arm_id and self.enrollment.class_arm_id != self.fee_schedule.class_arm_id)
        ):
            raise ValidationError({"enrollment": "The student is not enrolled in this fee schedule's class and session."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class SchoolFeePayment(models.Model):
    class Channel(models.TextChoices):
        PHYSICAL = "physical", "At school"
        ONLINE = "online", "Online"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        POS = "pos", "POS"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CARD = "card", "Card"
        USSD = "ussd", "USSD"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"
        PARTIALLY_REVERSED = "partially_reversed", "Partially reversed"
        REVERSED = "reversed", "Reversed"
        REFUNDED = "refunded", "Refunded"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="school_fee_payments")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    method = models.CharField(max_length=20, choices=Method.choices)
    provider = models.CharField(max_length=20, blank=True)
    reference = models.CharField(max_length=100, unique=True)
    provider_transaction_id = models.CharField(max_length=120, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="school_fee_payments")
    guardian = models.ForeignKey(Guardian, null=True, blank=True, on_delete=models.PROTECT, related_name="school_fee_payments")
    payer_email = models.EmailField(blank=True)
    description = models.CharField(max_length=300, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="school_fee_payments_recorded")
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.CheckConstraint(condition=Q(amount_minor__gt=0), name="school_fee_payment_positive_amount")]
        indexes = [models.Index(fields=("school", "status", "created_at"), name="fee_payment_school_status_idx")]


class FeePaymentAllocation(models.Model):
    payment = models.ForeignKey(SchoolFeePayment, on_delete=models.PROTECT, related_name="allocations")
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_payment_allocations")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_payment_allocations")
    fee_charge = models.ForeignKey(FeeCharge, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_allocations")
    amount_minor = models.PositiveBigIntegerField()
    balance_before_minor = models.PositiveBigIntegerField(null=True, blank=True)
    balance_after_minor = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        constraints = [models.CheckConstraint(condition=Q(amount_minor__gt=0), name="fee_allocation_positive_amount")]

    def clean(self):
        super().clean()
        if self.payment_id and self.payment.school_id != self.school_id:
            raise ValidationError({"payment": "The payment belongs to another school."})
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({"student": "The student belongs to another school."})
        if self.fee_charge_id and (self.fee_charge.school_id != self.school_id or self.fee_charge.student_id != self.student_id):
            raise ValidationError({"fee_charge": "The fee charge does not belong to this student and school."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PaymentReversal(models.Model):
    payment = models.ForeignKey(SchoolFeePayment, on_delete=models.PROTECT, related_name="reversals")
    amount_minor = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=500)
    external_reference = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="school_fee_reversals_recorded")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="fee_reversal_positive_amount"),
            models.UniqueConstraint(fields=("payment", "external_reference"), condition=~Q(external_reference=""), name="fee_reversal_external_ref_unique"),
        ]


class FeeLedgerEntry(models.Model):
    class Kind(models.TextChoices):
        CHARGE = "charge", "Fee issued"
        PAYMENT = "payment", "Payment allocation"
        ADJUSTMENT = "adjustment", "Adjustment"
        REFUND = "refund", "Refund or reversal"
        CREDIT_APPLICATION = "credit_application", "Credit applied"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_ledger_entries")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_ledger_entries")
    fee_charge = models.ForeignKey(FeeCharge, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    payment = models.ForeignKey(SchoolFeePayment, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    allocation = models.ForeignKey(FeePaymentAllocation, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    reversal = models.ForeignKey(PaymentReversal, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount_minor = models.BigIntegerField(help_text="Signed ledger amount in kobo. Charges are positive; payments are negative.")
    description = models.CharField(max_length=300)
    reference_key = models.CharField(max_length=180, unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="school_fee_ledger_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [models.CheckConstraint(condition=~Q(amount_minor=0), name="fee_ledger_nonzero_amount")]
        indexes = [models.Index(fields=("school", "student", "fee_charge", "created_at"), name="fee_ledger_balance_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Fee ledger entries are immutable.")
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({"student": "The student belongs to another school."})
        if self.fee_charge_id and (self.fee_charge.school_id != self.school_id or self.fee_charge.student_id != self.student_id):
            raise ValidationError({"fee_charge": "The fee charge does not belong to this student and school."})
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Fee ledger entries cannot be deleted.")


class PaymentProviderEvent(models.Model):
    class Provider(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"
        FLUTTERWAVE = "flutterwave", "Flutterwave"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    event_id = models.CharField(max_length=160)
    payment = models.ForeignKey(SchoolFeePayment, null=True, blank=True, on_delete=models.PROTECT, related_name="provider_events")
    event_type = models.CharField(max_length=100, blank=True)
    payload_hash = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "event_id"), name="fee_provider_event_unique")]
        indexes = [models.Index(fields=("provider", "received_at"), name="fee_provider_event_idx")]


class ReceiptOtpChallenge(models.Model):
    payment = models.ForeignKey(SchoolFeePayment, on_delete=models.CASCADE, related_name="receipt_otps")
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="fee_receipt_otps")
    phone_snapshot = models.CharField(max_length=30)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("payment", "guardian", "created_at"), name="fee_receipt_otp_lookup_idx")]


class FeeNotification(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    class Kind(models.TextChoices):
        PAYMENT_RECEIPT = "payment_receipt", "Payment receipt"
        RECEIPT_OTP = "receipt_otp", "Receipt verification code"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fee_notifications")
    payment = models.ForeignKey(SchoolFeePayment, on_delete=models.CASCADE, related_name="notifications")
    guardian = models.ForeignKey(Guardian, null=True, blank=True, on_delete=models.PROTECT, related_name="fee_notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    phone = models.CharField(max_length=30)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=120, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("school", "status", "created_at"), name="fee_notification_retry_idx")]
