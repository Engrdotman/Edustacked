from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, GradingScale, Subject, Term
from apps.schools.models import School
from apps.students.models import Student, StudentEnrollment


class AssessmentComponent(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="assessment_components")
    name = models.CharField(max_length=100)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("100.00"))
    default_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", name="assessment_component_school_name_ci_uniq"),
            models.CheckConstraint(condition=Q(max_score__gt=0), name="assessment_component_max_positive"),
            models.CheckConstraint(condition=Q(default_weight__isnull=True) | Q(default_weight__gt=0, default_weight__lte=100), name="assessment_component_weight_positive"),
        ]

    def clean(self):
        super().clean()
        if self.max_score is None or self.max_score <= 0:
            raise ValidationError({"max_score": "Maximum score must be greater than zero."})
        if self.default_weight is not None and not Decimal("0") < self.default_weight <= Decimal("100"):
            raise ValidationError({"default_weight": "A default weight must be greater than zero and no more than 100%."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.plan_usages.exists():
            raise ValidationError("Assessment components used by plans cannot be deleted; deactivate them instead.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.name


class AssessmentPlan(models.Model):
    class CalculationMethod(models.TextChoices):
        RAW = "raw", "Raw score addition"
        WEIGHTED = "weighted", "Weighted components"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published for entry"
        CLOSED = "closed", "Closed"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="assessment_plans")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="assessment_plans")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="assessment_plans")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="assessment_plans")
    class_arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="assessment_plans")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="assessment_plans")
    grading_scale = models.ForeignKey(GradingScale, on_delete=models.PROTECT, related_name="assessment_plans")
    name = models.CharField(max_length=120)
    calculation_method = models.CharField(max_length=10, choices=CalculationMethod.choices, default=CalculationMethod.RAW)
    grading_scale_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_assessment_plans")
    published_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="published_assessment_plans")
    closed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="closed_assessment_plans")
    reopened_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="reopened_assessment_plans")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "name")
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", "term", "class_arm", "subject", name="assessment_plan_slot_name_ci_uniq"),
        ]
        indexes = [models.Index(fields=("school", "academic_session", "term", "status"), name="assess_plan_scope_status_idx")]

    def clean(self):
        super().clean()
        for field, obj_id, obj in (
            ("academic_session", self.academic_session_id, self.academic_session),
            ("term", self.term_id, self.term), ("class_level", self.class_level_id, self.class_level),
            ("class_arm", self.class_arm_id, self.class_arm), ("subject", self.subject_id, self.subject),
            ("grading_scale", self.grading_scale_id, self.grading_scale),
        ):
            if obj_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field.replace('_', ' ')} belongs to another school."})
        if self.term_id and self.academic_session_id and self.term.academic_session_id != self.academic_session_id:
            raise ValidationError({"term": "The term must belong to the selected academic session."})
        if self.academic_session_id and self.academic_session.status == AcademicSession.Status.COMPLETED:
            raise ValidationError({"academic_session": "A new assessment plan cannot be created in a completed session."})
        if self.term_id and self.term.status == Term.Status.COMPLETED:
            raise ValidationError({"term": "A new assessment plan cannot be created in a completed term."})
        if self.class_arm_id and self.class_level_id and self.class_arm.class_level_id != self.class_level_id:
            raise ValidationError({"class_arm": "The arm must belong to the selected class."})
        if self.class_level_id and not self.class_level.is_active:
            raise ValidationError({"class_level": "Assessment plans require an active class."})
        if self.class_arm_id and not self.class_arm.is_active:
            raise ValidationError({"class_arm": "Assessment plans require an active class arm."})
        if self.subject_id and not self.subject.is_active:
            raise ValidationError({"subject": "Assessment plans require an active subject."})
        if self.class_level_id and self.subject_id:
            from apps.academics.models import ClassSubject
            configured = ClassSubject.objects.filter(school_id=self.school_id, class_level_id=self.class_level_id, is_active=True)
            if configured.exists() and not configured.filter(subject_id=self.subject_id).exists():
                raise ValidationError({"subject": "The subject is not assigned to this class."})
        if self.grading_scale_id and (not self.grading_scale.is_active or self.grading_scale.maximum_score <= 0):
            raise ValidationError({"grading_scale": "Select an active grading scale."})
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).first()
            if old and old.status != self.status:
                allowed = {
                    self.Status.DRAFT: {self.Status.PUBLISHED},
                    self.Status.PUBLISHED: {self.Status.CLOSED},
                    self.Status.CLOSED: {self.Status.PUBLISHED},
                }
                if self.status not in allowed.get(old.status, set()):
                    raise ValidationError({"status": "This assessment plan state transition is not allowed."})
                if old.status == self.Status.CLOSED and not self.reopened_by_id:
                    raise ValidationError({"status": "Use the authorized plan reopen action."})
            if old and old.status == self.Status.CLOSED and self.status != self.Status.CLOSED and not self.reopened_by_id:
                raise ValidationError({"status": "Use the authorized plan reopen action."})
            if old and old.status == self.Status.CLOSED and any(
                getattr(old, field) != getattr(self, field)
                for field in ("school_id", "academic_session_id", "term_id", "class_level_id", "class_arm_id", "subject_id", "grading_scale_id", "name", "calculation_method", "grading_scale_snapshot")
            ):
                raise ValidationError("Closed assessment plan configuration is immutable.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.results.exists() or self.audit_events.exists():
            raise ValidationError("Assessment plans with result history cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.name}: {self.class_level}/{self.class_arm} - {self.subject}"


class PlanComponent(models.Model):
    plan = models.ForeignKey(AssessmentPlan, on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey(AssessmentComponent, on_delete=models.PROTECT, related_name="plan_usages")
    max_score = models.DecimalField(max_digits=7, decimal_places=2)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    position = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("plan", "component"), name="plan_component_once_uniq"),
            models.UniqueConstraint(fields=("plan", "position"), name="plan_component_position_uniq"),
            models.CheckConstraint(condition=Q(max_score__gt=0), name="plan_component_max_positive"),
            models.CheckConstraint(condition=Q(weight__isnull=True) | Q(weight__gt=0, weight__lte=100), name="plan_component_weight_positive"),
        ]

    def clean(self):
        super().clean()
        if self.plan_id and self.component_id and self.plan.school_id != self.component.school_id:
            raise ValidationError({"component": "The component belongs to another school."})
        if self.max_score is None or self.max_score <= 0:
            raise ValidationError({"max_score": "Maximum score must be greater than zero."})
        if self.plan_id:
            if self.plan.status != AssessmentPlan.Status.DRAFT:
                raise ValidationError({"plan": "Components can only be configured while the plan is a draft."})
            if self.plan.results.filter(scores__isnull=False).exists():
                raise ValidationError({"plan": "Components are locked after score entry begins."})
            if self.plan.calculation_method == AssessmentPlan.CalculationMethod.WEIGHTED and (self.weight is None or not Decimal("0") < self.weight <= Decimal("100")):
                raise ValidationError({"weight": "Weighted plan components require a weight greater than zero and no more than 100%."})
            if self.plan.calculation_method == AssessmentPlan.CalculationMethod.RAW and self.weight is not None:
                raise ValidationError({"weight": "Raw score plans do not use component weights."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.plan.status != AssessmentPlan.Status.DRAFT:
            raise ValidationError("Components can only be removed from a draft plan.")
        if self.plan.results.filter(scores__isnull=False).exists():
            raise ValidationError("Plan components cannot be removed after score entry begins.")
        return super().delete(*args, **kwargs)


class AssessmentResult(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="assessment_results")
    plan = models.ForeignKey(AssessmentPlan, on_delete=models.PROTECT, related_name="results")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="assessment_results")
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="assessment_results")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    approved_total = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    approved_maximum = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    approved_percentage = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    approved_grade = models.CharField(max_length=20, blank=True)
    approved_grade_point = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    approved_calculation = models.JSONField(default=dict, blank=True)
    submitted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="submitted_assessment_results")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_assessment_results")
    reopened_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="reopened_assessment_results")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student__last_name", "student__first_name")
        constraints = [models.UniqueConstraint(fields=("plan", "student"), name="assessment_result_plan_student_uniq")]
        indexes = [models.Index(fields=("school", "plan", "status"), name="assess_result_school_plan_idx")]

    def clean(self):
        super().clean()
        for field, obj_id, obj in (("plan", self.plan_id, self.plan), ("student", self.student_id, self.student), ("enrollment", self.enrollment_id, self.enrollment)):
            if obj_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field} belongs to another school."})
        if self.plan_id and self.enrollment_id:
            if self.enrollment.student_id != self.student_id or self.enrollment.academic_session_id != self.plan.academic_session_id:
                raise ValidationError({"enrollment": "Enrollment must match the student and plan session."})
            if self.enrollment.class_level_id != self.plan.class_level_id or self.enrollment.class_arm_id != self.plan.class_arm_id:
                raise ValidationError({"enrollment": "Enrollment must match the plan class and arm."})
            term = self.plan.term
            enrollment = self.enrollment
            valid = enrollment.enrollment_date <= term.end_date
            if enrollment.status == StudentEnrollment.Status.WITHDRAWN:
                valid = valid and enrollment.withdrawal_date is not None and enrollment.withdrawal_date >= term.start_date
            elif enrollment.status == StudentEnrollment.Status.TRANSFERRED:
                valid = valid and enrollment.transfer_date is not None and enrollment.transfer_date >= term.start_date
            elif enrollment.status not in (StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED):
                valid = False
            if not valid:
                raise ValidationError({"enrollment": "This enrollment is not eligible during the plan term."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.status != self.status:
                allowed = {
                    self.Status.DRAFT: {self.Status.SUBMITTED},
                    self.Status.SUBMITTED: {self.Status.APPROVED},
                    self.Status.APPROVED: {self.Status.DRAFT},
                }
                if self.status not in allowed.get(previous.status, set()):
                    raise ValidationError({"status": "This result state transition is not allowed."})
                if previous.status == self.Status.APPROVED and not self.reopened_by_id:
                    raise ValidationError({"status": "Use the authorized result reopen workflow."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Assessment results cannot be deleted; use the correction workflow.")


class ComponentScore(models.Model):
    result = models.ForeignKey(AssessmentResult, on_delete=models.CASCADE, related_name="scores")
    plan_component = models.ForeignKey(PlanComponent, on_delete=models.PROTECT, related_name="scores")
    score = models.DecimalField(max_digits=7, decimal_places=2)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="recorded_component_scores")
    last_modified_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="modified_component_scores")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("result", "plan_component"), name="component_score_result_component_uniq"),
            models.CheckConstraint(condition=Q(score__gte=0), name="component_score_nonnegative"),
        ]
        ordering = ("plan_component__position",)

    def clean(self):
        super().clean()
        if self.result_id and self.plan_component_id and self.result.plan_id != self.plan_component.plan_id:
            raise ValidationError({"plan_component": "The component is not part of this result's plan."})
        if self.score is None or self.score < 0:
            raise ValidationError({"score": "Score cannot be negative."})
        if self.plan_component_id and self.score > self.plan_component.max_score:
            raise ValidationError({"score": f"Score cannot exceed {self.plan_component.max_score}."})
        if self.result_id and self.result.status != AssessmentResult.Status.DRAFT:
            raise ValidationError({"result": "Scores can only change while a result is a draft."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Scores cannot be deleted; reopen the result and correct its value.")


class ResultAuditEvent(models.Model):
    class EventType(models.TextChoices):
        SCORE_RECORDED = "score_recorded", "Score recorded"
        SCORE_CORRECTED = "score_corrected", "Score corrected"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REOPENED = "reopened", "Reopened"
        PLAN_PUBLISHED = "plan_published", "Plan published"
        PLAN_CLOSED = "plan_closed", "Plan closed"
        PLAN_REOPENED = "plan_reopened", "Plan reopened"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="result_audit_events")
    plan = models.ForeignKey(AssessmentPlan, on_delete=models.PROTECT, related_name="audit_events")
    result = models.ForeignKey(AssessmentResult, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    plan_component = models.ForeignKey(PlanComponent, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="result_audit_events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    previous_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Result audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Result audit events cannot be deleted.")
