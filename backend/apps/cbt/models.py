from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string, constant_time_compare
from hashlib import sha256

from apps.academics.models import AcademicSession, ClassLevel, Subject, Term
from apps.schools.models import School
from apps.students.models import Student


MAX_QUESTION_IMAGE_SIZE = 3 * 1024 * 1024


def validate_question_image_size(value):
    if value.size > MAX_QUESTION_IMAGE_SIZE:
        raise ValidationError("Question images must be 3 MB or smaller.")


def question_image_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"cbt-questions/{instance.school_id}/{uuid4().hex}{extension}"


class Question(models.Model):
    class Type(models.TextChoices):
        SINGLE_CHOICE = "single_choice", "Single choice"
        MULTIPLE_ANSWER = "multiple_answer", "Multiple answer"
        TEXT = "text", "Text response"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="cbt_questions")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="cbt_questions")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="cbt_questions")
    topic = models.CharField(max_length=160, blank=True)
    text = models.TextField()
    question_type = models.CharField(max_length=20, choices=Type.choices)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    marks = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    explanation = models.TextField(blank=True)
    image = models.ImageField(
        upload_to=question_image_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_question_image_size],
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cbt_questions_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("school", "subject", "status"), name="cbt_question_school_subj_idx"),
            models.Index(fields=("school", "class_level", "difficulty"), name="cbt_question_school_class_idx"),
        ]
        constraints = [models.CheckConstraint(condition=Q(marks__gt=0), name="cbt_question_marks_positive")]

    def clean(self):
        super().clean()
        if self.subject_id and self.school_id and self.subject.school_id != self.school_id:
            raise ValidationError({"subject": "The selected subject belongs to another school."})
        if self.class_level_id and self.school_id and self.class_level.school_id != self.school_id:
            raise ValidationError({"class_level": "The selected class belongs to another school."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject}: {self.text[:80]}"


class QuestionOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.TextField()
    position = models.PositiveSmallIntegerField(default=0)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("question", "position"), name="cbt_option_question_position_uniq")]

    def __str__(self):
        return f"Option {self.position + 1} for {self.question_id}"


class Examination(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SCHEDULED = "scheduled", "Scheduled"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    class SelectionMethod(models.TextChoices):
        MANUAL = "manual", "Manually selected"
        RANDOM = "random", "Random from question bank"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="cbt_examinations")
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="cbt_examinations")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="cbt_examinations")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="cbt_examinations")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.PROTECT, related_name="cbt_examinations")
    duration_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    pass_mark = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    randomize_question_order = models.BooleanField(default=False)
    randomize_answer_options = models.BooleanField(default=False)
    maximum_attempts = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    selection_method = models.CharField(max_length=10, choices=SelectionMethod.choices, default=SelectionMethod.MANUAL)
    random_question_count = models.PositiveSmallIntegerField(null=True, blank=True)
    question_criteria = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cbt_examinations_created")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("school", "status", "starts_at"), name="cbt_exam_school_status_idx"),
            models.Index(fields=("school", "academic_session", "class_level"), name="cbt_exam_school_class_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="cbt_exam_schedule_ordered"),
            models.CheckConstraint(condition=Q(duration_minutes__gt=0), name="cbt_exam_duration_positive"),
            models.CheckConstraint(condition=Q(maximum_attempts__gt=0), name="cbt_exam_attempts_positive"),
        ]

    @property
    def is_frozen(self):
        return self.published_at is not None

    def clean(self):
        super().clean()
        for field in ("subject", "class_level", "academic_session", "term"):
            object_id = getattr(self, f"{field}_id", None)
            related = getattr(self, field, None) if object_id else None
            if related and related.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field.replace('_', ' ')} belongs to another school."})
        if self.term_id and self.term.academic_session_id != self.academic_session_id:
            raise ValidationError({"term": "The selected term belongs to another academic session."})
        if self.academic_session_id and self.starts_at and self.ends_at:
            session = self.academic_session
            start_date = timezone.localtime(self.starts_at).date()
            end_date = timezone.localtime(self.ends_at).date()
            if start_date < session.start_date or end_date > session.end_date:
                raise ValidationError({"starts_at": "The examination schedule must fall within the academic session."})
        if self.term_id and self.starts_at and self.ends_at:
            start_date = timezone.localtime(self.starts_at).date()
            end_date = timezone.localtime(self.ends_at).date()
            if start_date < self.term.start_date or end_date > self.term.end_date:
                raise ValidationError({"starts_at": "The examination schedule must fall within the selected term."})
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End time must be after start time."})
        if self.selection_method == self.SelectionMethod.RANDOM and not self.random_question_count:
            raise ValidationError({"random_question_count": "Set how many questions to select randomly."})
        if self.selection_method == self.SelectionMethod.MANUAL and self.random_question_count:
            raise ValidationError({"random_question_count": "This field is only used for random selection."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ExaminationQuestion(models.Model):
    """Draft question selection which becomes an immutable-at-the-content-level snapshot on publish."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="exam_questions")
    source_question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="exam_selections")
    position = models.PositiveSmallIntegerField(default=0)
    prompt_snapshot = models.TextField(blank=True)
    type_snapshot = models.CharField(max_length=20, blank=True)
    options_snapshot = models.JSONField(default=list, blank=True)
    marks_snapshot = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    explanation_snapshot = models.TextField(blank=True)
    is_snapshot = models.BooleanField(default=False)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("examination", "source_question"), name="cbt_exam_question_uniq"),
            models.UniqueConstraint(fields=("examination", "position"), name="cbt_exam_position_uniq"),
        ]

    def clean(self):
        super().clean()
        if self.examination_id and self.source_question_id:
            examination = self.examination
            question = self.source_question
            if question.school_id != examination.school_id:
                raise ValidationError({"source_question": "The selected question belongs to another school."})
            if question.subject_id != examination.subject_id or question.class_level_id != examination.class_level_id:
                raise ValidationError({"source_question": "The selected question does not match the examination subject and class."})
            if examination.is_frozen and not self._state.adding:
                previous = type(self).objects.filter(pk=self.pk, is_snapshot=True).first()
                if previous and any(getattr(previous, field) != getattr(self, field) for field in (
                    "source_question_id", "position", "prompt_snapshot", "type_snapshot", "options_snapshot", "marks_snapshot", "explanation_snapshot"
                )):
                    raise ValidationError("Published examination question snapshots are immutable.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def snapshot(self):
        question = self.source_question
        self.prompt_snapshot = question.text
        self.type_snapshot = question.question_type
        self.marks_snapshot = question.marks
        self.explanation_snapshot = question.explanation
        self.options_snapshot = [
            {"text": option.text, "is_correct": option.is_correct}
            for option in question.options.all()
        ]
        self.is_snapshot = True
        self.save(update_fields=("prompt_snapshot", "type_snapshot", "marks_snapshot", "explanation_snapshot", "options_snapshot", "is_snapshot"))


class ExaminationAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="assignments")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="cbt_assignments")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cbt_assignments_created")
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student__last_name", "student__first_name")
        constraints = [models.UniqueConstraint(fields=("examination", "student"), name="cbt_assignment_exam_student_uniq")]
        indexes = [models.Index(fields=("examination", "status"), name="cbt_assignment_exam_status_idx")]

    def clean(self):
        super().clean()
        if self.examination_id and self.student_id:
            exam = self.examination
            if self.student.school_id != exam.school_id:
                raise ValidationError({"student": "The selected student belongs to another school."})
            eligible = exam.school.student_enrollments.filter(
                student_id=self.student_id,
                academic_session_id=exam.academic_session_id,
                class_level_id=exam.class_level_id,
                status="active",
                student__status=Student.Status.ACTIVE,
            ).exists()
            if not eligible:
                raise ValidationError({"student": "The student is not actively enrolled in this examination's class and session."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class LocalCbtServerCredential(models.Model):
    """Per-school bearer credential for one local CBT server; plaintext is shown once."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="cbt_local_servers")
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("school", "name")

    @staticmethod
    def issue(school, name):
        token = get_random_string(64)
        credential = LocalCbtServerCredential.objects.create(
            school=school,
            name=name,
            token_hash=sha256(token.encode("utf-8")).hexdigest(),
        )
        return credential, token

    @classmethod
    def authenticate_token(cls, token):
        digest = sha256((token or "").encode("utf-8")).hexdigest()
        credential = cls.objects.filter(token_hash=digest, is_active=True).select_related("school").first()
        if credential and constant_time_compare(credential.token_hash, digest):
            credential.last_seen_at = timezone.now()
            credential.save(update_fields=("last_seen_at",))
            return credential
        return None


class LocalCbtSyncEvent(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        CONFLICT = "conflict", "Conflict"
        REJECTED = "rejected", "Rejected"

    event_id = models.UUIDField(primary_key=True)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="cbt_sync_events")
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="sync_events")
    assignment = models.ForeignKey(ExaminationAssignment, on_delete=models.PROTECT, related_name="sync_events")
    local_session_id = models.UUIDField()
    payload_version = models.PositiveSmallIntegerField(default=1)
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACCEPTED)
    resolution_note = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)
        indexes = [models.Index(fields=("school", "status", "received_at"), name="cbt_sync_school_status_idx")]
        constraints = [models.UniqueConstraint(fields=("school", "local_session_id"), name="cbt_sync_school_session_uniq")]


class CbtExaminationPackage(models.Model):
    package_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="cbt_packages")
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="offline_packages")
    version = models.PositiveSmallIntegerField(default=1)
    payload_hash = models.CharField(max_length=64)
    signed_payload = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cbt_packages_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("examination", "version"), name="cbt_package_exam_version_uniq")]

    def __str__(self):
        return f"{self.examination.title} package v{self.version}"


class CbtSyncConflict(models.Model):
    event = models.ForeignKey(LocalCbtSyncEvent, on_delete=models.PROTECT, related_name="conflicts")
    attempted_hash = models.CharField(max_length=64)
    attempted_payload = models.JSONField()
    reason = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class CbtSyncedSubmission(models.Model):
    """Immutable raw local submission snapshot, not a Phase 5 scored result."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="cbt_synced_submissions")
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="synced_submissions")
    assignment = models.ForeignKey(ExaminationAssignment, on_delete=models.PROTECT, related_name="synced_submissions")
    local_session_id = models.UUIDField()
    event = models.OneToOneField(LocalCbtSyncEvent, on_delete=models.PROTECT, related_name="submission")
    submitted_at = models.DateTimeField()
    answers = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("school", "local_session_id"), name="cbt_synced_submission_session_uniq")]
        indexes = [models.Index(fields=("school", "examination", "submitted_at"), name="cbt_submission_school_exam_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Synchronized submissions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Synchronized submissions cannot be deleted.")


class CbtResult(models.Model):
    """Immutable calculated result snapshot for one synchronized local attempt."""

    class Status(models.TextChoices):
        NEEDS_MARKING = "needs_marking", "Needs manual marking"
        FINALIZED = "finalized", "Finalized"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="cbt_results")
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="results")
    assignment = models.ForeignKey(ExaminationAssignment, on_delete=models.PROTECT, related_name="results")
    event = models.OneToOneField(LocalCbtSyncEvent, on_delete=models.PROTECT, related_name="result")
    local_session_id = models.UUIDField()
    submitted_at = models.DateTimeField()
    synchronized_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices)
    total_questions = models.PositiveSmallIntegerField()
    attempted_questions = models.PositiveSmallIntegerField()
    unanswered_questions = models.PositiveSmallIntegerField()
    correct_answers = models.PositiveSmallIntegerField()
    incorrect_answers = models.PositiveSmallIntegerField()
    objective_score = models.DecimalField(max_digits=9, decimal_places=2)
    pass_mark = models.DecimalField(max_digits=9, decimal_places=2)
    score = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    maximum_score = models.DecimalField(max_digits=9, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    mark_details = models.JSONField(default=list)
    calculated_by = models.CharField(max_length=80, default="system:offline-cbt-auto-mark-v1")
    calculated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-submitted_at",)
        constraints = [
            models.UniqueConstraint(fields=("school", "local_session_id"), name="cbt_result_school_session_uniq"),
        ]
        indexes = [
            models.Index(fields=("school", "examination", "status"), name="cbt_result_school_exam_idx"),
            models.Index(fields=("school", "submitted_at"), name="cbt_result_school_date_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Finalized CBT result snapshots can only change through the audited result service.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("CBT result records cannot be deleted.")


class CbtResultCorrection(models.Model):
    """Append-only audit record for manual marks and authorized corrections."""

    result = models.ForeignKey(CbtResult, on_delete=models.PROTECT, related_name="corrections")
    corrected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cbt_result_corrections")
    reason = models.CharField(max_length=500)
    previous_details = models.JSONField()
    corrected_details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("CBT result correction audits are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("CBT result correction audits cannot be deleted.")
