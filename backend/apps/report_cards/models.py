from django.core.exceptions import ValidationError
from django.db import models

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.models import School
from apps.students.models import Student, StudentEnrollment


class ReportCard(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Ready for review"
        APPROVED = "approved", "Approved"
        FINALIZED = "finalized", "Finalized / published"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="report_cards")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="report_cards")
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="report_cards")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="report_cards")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="report_cards")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="report_cards")
    class_arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="report_cards")
    identifier = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    current_revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_report_cards")
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_report_cards")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_report_cards")
    finalized_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="finalized_report_cards")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("student__last_name", "student__first_name")
        constraints = [models.UniqueConstraint(fields=("school", "student", "enrollment", "academic_session", "term"), name="report_card_student_term_enrollment_uniq")]
        indexes = [models.Index(fields=("school", "academic_session", "term", "class_level", "class_arm", "status"), name="report_card_scope_status_idx")]

    def clean(self):
        super().clean()
        pairs = (("student", self.student_id, self.student), ("enrollment", self.enrollment_id, self.enrollment), ("academic_session", self.academic_session_id, self.academic_session), ("term", self.term_id, self.term), ("class_level", self.class_level_id, self.class_level), ("class_arm", self.class_arm_id, self.class_arm))
        for field, object_id, obj in pairs:
            if object_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: "All report card records must belong to the same school."})
        if self.class_arm_id and self.class_level_id and self.class_arm.class_level_id != self.class_level_id:
            raise ValidationError({"class_arm": "The arm must belong to the selected class."})
        if self.term_id and self.academic_session_id and self.term.academic_session_id != self.academic_session_id:
            raise ValidationError({"term": "The term must belong to the selected session."})
        if self.enrollment_id:
            enrollment = self.enrollment
            if enrollment.student_id != self.student_id or enrollment.academic_session_id != self.academic_session_id or enrollment.class_level_id != self.class_level_id or enrollment.class_arm_id != self.class_arm_id:
                raise ValidationError({"enrollment": "Enrollment must match the report card student, session, class, and arm."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous:
                identity_fields = ("school_id", "student_id", "enrollment_id", "academic_session_id", "term_id", "class_level_id", "class_arm_id", "identifier")
                if any(getattr(previous, field) != getattr(self, field) for field in identity_fields):
                    raise ValidationError("A report card's school, student, enrollment, term, class, and identifier are immutable.")
                if previous.status != self.status:
                    allowed = {
                        self.Status.DRAFT: {self.Status.REVIEW},
                        self.Status.REVIEW: {self.Status.APPROVED, self.Status.DRAFT},
                        self.Status.APPROVED: {self.Status.FINALIZED, self.Status.DRAFT},
                        self.Status.FINALIZED: {self.Status.DRAFT},
                    }
                    if self.status not in allowed.get(previous.status, set()):
                        raise ValidationError({"status": "This report-card state transition is not allowed."})
                    if previous.status == self.Status.FINALIZED and self.current_revision <= previous.current_revision:
                        raise ValidationError({"current_revision": "Starting a finalized report-card correction requires a new revision."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.revisions.filter(status=self.Status.FINALIZED).exists():
            raise ValidationError("A report card with an official finalized revision cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.identifier


class ReportCardRevision(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Ready for review"
        APPROVED = "approved", "Approved"
        FINALIZED = "finalized", "Finalized"
        RETURNED = "returned", "Returned for correction"

    report_card = models.ForeignKey(ReportCard, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    snapshot = models.JSONField(default=dict)
    validation_errors = models.JSONField(default=list, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    generated_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="generated_report_revisions")
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_report_revisions")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_report_revisions")
    finalized_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="finalized_report_revisions")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-revision_number",)
        constraints = [models.UniqueConstraint(fields=("report_card", "revision_number"), name="report_card_revision_number_uniq")]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.status == self.Status.FINALIZED:
                raise ValidationError("Finalized report-card revisions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.FINALIZED:
            raise ValidationError("Finalized report-card revisions cannot be deleted.")
        return super().delete(*args, **kwargs)


class ReportCardAuditEvent(models.Model):
    report_card = models.ForeignKey(ReportCard, on_delete=models.PROTECT, related_name="audit_events")
    revision = models.ForeignKey(ReportCardRevision, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="report_card_audit_events")
    action = models.CharField(max_length=30)
    reason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Report-card audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Report-card audit events cannot be deleted.")
