from uuid import uuid4

from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ImportLog(models.Model):
    package_id = models.UUIDField(null=True, blank=True)
    examination_id = models.CharField(max_length=36, blank=True)
    status = models.CharField(max_length=16)
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ImportedExamination(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        EXPIRED = "expired", "Expired"
        DISABLED = "disabled", "Disabled"

    package_id = models.UUIDField(primary_key=True)
    school_id = models.PositiveBigIntegerField(db_index=True)
    examination_id = models.CharField(max_length=36, db_index=True)
    version = models.PositiveSmallIntegerField()
    payload_hash = models.CharField(max_length=64)
    signed_payload = models.TextField(blank=True)
    config = models.JSONField()
    answer_key = models.JSONField()
    assigned_student_ids = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.READY)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("examination_id", "version"), name="local_exam_version_uniq")]
        indexes = [models.Index(fields=("school_id", "status"), name="local_pkg_school_status_idx")]

    def __str__(self):
        return f"{self.config.get('title', self.examination_id)} v{self.version}"


class LocalStudentCredential(models.Model):
    central_student_id = models.PositiveBigIntegerField(unique=True)
    admission_number = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=240)
    password_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def __str__(self):
        return f"{self.admission_number} — {self.display_name}"


class StudentAccessToken(models.Model):
    student = models.ForeignKey(LocalStudentCredential, on_delete=models.CASCADE, related_name="tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_valid(self):
        return self.revoked_at is None and self.expires_at > timezone.now() and self.student.is_active


class LocalExamSession(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Auto-submitted"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    exam = models.ForeignKey(ImportedExamination, on_delete=models.PROTECT, related_name="sessions")
    student = models.ForeignKey(LocalStudentCredential, on_delete=models.PROTECT, related_name="exam_sessions")
    assignment_id = models.UUIDField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    client_request_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=("student", "status", "started_at"), name="local_session_student_idx"),
            models.Index(fields=("exam", "status"), name="local_session_exam_status_idx"),
        ]
        constraints = [models.UniqueConstraint(
            fields=("student", "exam"), condition=Q(status="in_progress"), name="local_student_one_active_exam_uniq"
        )]

    def save(self, *args, **kwargs):
        if self.pk and LocalExamSession.objects.filter(pk=self.pk, status__in=(self.Status.SUBMITTED, self.Status.AUTO_SUBMITTED)).exists():
            old = LocalExamSession.objects.get(pk=self.pk)
            immutable = ("exam_id", "student_id", "assignment_id", "started_at", "expires_at", "submitted_at")
            if any(getattr(old, field) != getattr(self, field) for field in immutable) or self.status != old.status:
                raise ValidationError("Completed local examination sessions are immutable.")
        return super().save(*args, **kwargs)


class LocalStudentAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    session = models.ForeignKey(LocalExamSession, on_delete=models.PROTECT, related_name="answers")
    question_id = models.CharField(max_length=36)
    value = models.JSONField()
    last_request_id = models.UUIDField()
    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("session", "question_id"), name="local_answer_session_question_uniq"),
            models.UniqueConstraint(fields=("session", "last_request_id"), name="local_answer_request_uniq"),
        ]
        indexes = [models.Index(fields=("session", "saved_at"), name="local_answer_session_saved_idx")]


class AnswerSaveRequest(models.Model):
    session = models.ForeignKey(LocalExamSession, on_delete=models.PROTECT, related_name="save_requests")
    request_id = models.UUIDField()
    question_id = models.CharField(max_length=36)
    value_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("session", "request_id"), name="local_answer_request_session_uniq")]


class LocalSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    session = models.OneToOneField(LocalExamSession, on_delete=models.PROTECT, related_name="submission")
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    answers = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    submitted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Local submissions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Local submissions cannot be deleted.")


class SyncOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed; manual retry available"

    event_id = models.UUIDField(primary_key=True)
    session = models.OneToOneField(LocalExamSession, on_delete=models.PROTECT, related_name="sync_event")
    event_type = models.CharField(max_length=48, default="submission.finalized")
    payload_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    retry_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    error_detail = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("status", "next_attempt_at"), name="local_outbox_due_idx")]

    def save(self, *args, **kwargs):
        if self.pk and SyncOutbox.objects.filter(pk=self.pk, status=self.Status.SYNCED).exists():
            old = SyncOutbox.objects.get(pk=self.pk)
            if old.payload_hash != self.payload_hash or self.status != old.status:
                raise ValidationError("Synchronized outbox entries are immutable.")
        return super().save(*args, **kwargs)


class SyncLog(models.Model):
    event_id = models.UUIDField(db_index=True)
    action = models.CharField(max_length=24)
    status = models.CharField(max_length=16)
    detail = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class LocalLicenseVerification(models.Model):
    license_id = models.UUIDField(unique=True)
    school_id = models.PositiveBigIntegerField(db_index=True)
    service_code = models.CharField(max_length=50)
    starts_on = models.DateField()
    expires_on = models.DateField()
    offline_grace_days = models.PositiveSmallIntegerField(default=7)
    last_verified_at = models.DateTimeField(auto_now_add=True)
    payload_hash = models.CharField(max_length=64)

    @property
    def valid_for_offline_use(self):
        today = timezone.localdate()
        return self.starts_on <= today <= self.expires_on + timedelta(days=self.offline_grace_days)


class LocalBackupRecord(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    size_bytes = models.PositiveBigIntegerField()
    integrity_check = models.CharField(max_length=16, default="ok")

    class Meta:
        ordering = ("-created_at",)


