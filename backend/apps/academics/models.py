from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.schools.models import School


class AcademicSession(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="academic_sessions")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_date", "name")
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", name="academic_session_school_name_ci_uniq"),
            models.UniqueConstraint(fields=("school",), condition=Q(status="active"), name="academic_session_one_active_per_school"),
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="academic_session_dates_ordered"),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be later than start date."})
        if not self.pk:
            if self.status != self.Status.DRAFT:
                raise ValidationError({"status": "New academic sessions must start as drafts."})
            return
        previous = type(self).objects.filter(pk=self.pk).first()
        if not previous:
            return
        changed = any(getattr(previous, field) != getattr(self, field) for field in ("school_id", "name", "start_date", "end_date"))
        if previous.status == self.Status.COMPLETED and (changed or self.status != previous.status):
            raise ValidationError("Completed academic sessions are immutable.")
        if previous.status == self.Status.DRAFT and self.status == self.Status.COMPLETED:
            raise ValidationError({"status": "A draft session must be activated before completion."})
        if previous.status == self.Status.ACTIVE and (changed or self.status == self.Status.DRAFT):
            raise ValidationError("Active session details are locked; complete it before changing the lifecycle.")
        if changed and self.terms.filter(
            Q(start_date__lt=self.start_date) | Q(end_date__gt=self.end_date)
        ).exists():
            raise ValidationError("Session dates cannot exclude dates already assigned to its terms.")
        if self.status == self.Status.COMPLETED and self.terms.exclude(status="completed").exists():
            raise ValidationError({"status": "Complete all session terms before completing the session."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Term(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="academic_terms")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="terms")
    name = models.CharField(max_length=60)
    sequence = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("academic_session", "sequence")
        constraints = [
            models.UniqueConstraint(Lower("name"), "academic_session", name="academic_term_session_name_ci_uniq"),
            models.UniqueConstraint(fields=("academic_session", "sequence"), name="academic_term_session_sequence_uniq"),
            models.UniqueConstraint(fields=("academic_session",), condition=Q(status="active"), name="academic_term_one_active_per_session"),
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="academic_term_dates_ordered"),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be later than start date."})
        if self.academic_session_id and self.school_id and self.academic_session.school_id != self.school_id:
            raise ValidationError({"academic_session": "The selected session belongs to another school."})
        if self.academic_session_id and self.academic_session.status == AcademicSession.Status.COMPLETED:
            raise ValidationError({"academic_session": "Terms cannot be changed after the session is completed."})
        if self.academic_session_id and self.start_date and self.end_date:
            session = self.academic_session
            if self.start_date < session.start_date or self.end_date > session.end_date:
                raise ValidationError("Term dates must fall within the academic session.")
            overlaps = type(self).objects.filter(
                academic_session_id=self.academic_session_id,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError({"start_date": "Term date ranges cannot overlap within a session."})
        if not self.pk:
            if self.status != self.Status.DRAFT:
                raise ValidationError({"status": "New terms must start as drafts."})
            return
        previous = type(self).objects.filter(pk=self.pk).first()
        if not previous:
            return
        changed = any(getattr(previous, field) != getattr(self, field) for field in ("school_id", "academic_session_id", "name", "sequence", "start_date", "end_date"))
        if previous.status == self.Status.COMPLETED and (changed or self.status != previous.status):
            raise ValidationError("Completed terms are immutable.")
        if previous.status == self.Status.DRAFT and self.status == self.Status.COMPLETED:
            raise ValidationError({"status": "A draft term must be activated before completion."})
        if previous.status == self.Status.ACTIVE and (changed or self.status == self.Status.DRAFT):
            raise ValidationError("Active term details are locked; complete it before changing the lifecycle.")
        if self.status == self.Status.ACTIVE and self.academic_session.status != AcademicSession.Status.ACTIVE:
            raise ValidationError({"status": "Only terms in the active academic session can be activated."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.academic_session.name} — {self.name}"


class ClassLevel(models.Model):
    class Category(models.TextChoices):
        EARLY_YEARS = "early_years", "Early years"
        PRIMARY = "primary", "Primary"
        JUNIOR_SECONDARY = "junior_secondary", "Junior secondary"
        SENIOR_SECONDARY = "senior_secondary", "Senior secondary"
        OTHER = "other", "Other"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_levels")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, blank=True)
    category = models.CharField(max_length=24, choices=Category.choices, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", name="class_level_school_name_ci_uniq"),
            models.UniqueConstraint(Lower("code"), "school", condition=~Q(code=""), name="class_level_school_code_ci_uniq"),
        ]

    def __str__(self):
        return self.name


class ClassArm(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_arms")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="arms")
    name = models.CharField(max_length=60)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("class_level__name", "name")
        constraints = [models.UniqueConstraint(Lower("name"), "class_level", name="class_arm_class_name_ci_uniq")]

    def clean(self):
        super().clean()
        if self.class_level_id and self.school_id and self.class_level.school_id != self.school_id:
            raise ValidationError({"class_level": "The selected class belongs to another school."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.class_level} — {self.name}"


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", name="subject_school_name_ci_uniq"),
            models.UniqueConstraint(Lower("code"), "school", condition=~Q(code=""), name="subject_school_code_ci_uniq"),
        ]

    def __str__(self):
        return self.name


class ClassSubject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_subjects")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="class_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="class_subjects")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("class_level__name", "subject__name")
        constraints = [models.UniqueConstraint(fields=("class_level", "subject"), name="class_subject_pair_uniq")]

    def clean(self):
        super().clean()
        if self.class_level_id and self.school_id and self.class_level.school_id != self.school_id:
            raise ValidationError({"class_level": "The selected class belongs to another school."})
        if self.subject_id and self.school_id and self.subject.school_id != self.school_id:
            raise ValidationError({"subject": "The selected subject belongs to another school."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class GradingScale(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="grading_scales")
    name = models.CharField(max_length=100)
    maximum_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"))
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(Lower("name"), "school", name="grading_scale_school_name_ci_uniq"),
            models.CheckConstraint(condition=Q(maximum_score__gt=0), name="grading_scale_max_score_positive"),
        ]

    def clean(self):
        super().clean()
        if self.maximum_score is None or self.maximum_score <= 0:
            raise ValidationError({"maximum_score": "Maximum score must be greater than zero."})
        bands = list(self.bands.filter(is_active=True).order_by("min_score", "max_score")) if self.pk else []
        if any(band.max_score > self.maximum_score for band in bands):
            raise ValidationError({"maximum_score": "Maximum score cannot be lower than an existing grade boundary."})
        if self.is_active:
            validate_grade_coverage(self.maximum_score, bands)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def validate_grade_coverage(maximum_score, bands):
    if not bands:
        raise ValidationError({"is_active": "Add grade bands before activating a grading scale."})
    if bands[0].min_score != Decimal("0.00"):
        raise ValidationError({"is_active": "Active grading bands must start at 0.00."})
    for previous, current in zip(bands, bands[1:]):
        if current.min_score != previous.max_score + Decimal("0.01"):
            raise ValidationError({"is_active": "Active grading bands must cover every hundredth without gaps or overlaps."})
    if bands[-1].max_score != maximum_score:
        raise ValidationError({"is_active": "Active grading bands must end at the configured maximum score."})


class GradeBand(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="grade_bands")
    grading_scale = models.ForeignKey(GradingScale, on_delete=models.PROTECT, related_name="bands")
    label = models.CharField(max_length=20)
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.CharField(max_length=200, blank=True)
    grade_point = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("min_score", "max_score", "label")
        constraints = [
            models.UniqueConstraint(Lower("label"), "grading_scale", name="grade_band_scale_label_ci_uniq"),
            models.CheckConstraint(condition=Q(min_score__gte=0), name="grade_band_min_nonnegative"),
            models.CheckConstraint(condition=Q(max_score__gte=F("min_score")), name="grade_band_range_ordered"),
            models.CheckConstraint(condition=Q(grade_point__isnull=True) | Q(grade_point__gte=0), name="grade_band_point_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if self.grading_scale_id and self.school_id and self.grading_scale.school_id != self.school_id:
            raise ValidationError({"grading_scale": "The selected grading scale belongs to another school."})
        if self.min_score is not None and self.max_score is not None:
            if self.min_score < 0 or self.max_score < self.min_score:
                raise ValidationError({"max_score": "Minimum and maximum score range is invalid."})
            if self.grading_scale_id and self.max_score > self.grading_scale.maximum_score:
                raise ValidationError({"max_score": "Grade boundaries cannot exceed the grading scale maximum."})
        if self.grading_scale_id and self.min_score is not None and self.max_score is not None:
            if self.is_active:
                overlap = type(self).objects.filter(
                    grading_scale_id=self.grading_scale_id,
                    is_active=True,
                    min_score__lte=self.max_score,
                    max_score__gte=self.min_score,
                ).exclude(pk=self.pk)
                if overlap.exists():
                    raise ValidationError({"min_score": "Active grade bands cannot overlap."})
            if self.grading_scale.is_active:
                bands = list(type(self).objects.filter(
                    grading_scale_id=self.grading_scale_id, is_active=True
                ).exclude(pk=self.pk).order_by("min_score", "max_score"))
                if self.is_active:
                    bands.append(self)
                    bands.sort(key=lambda band: (band.min_score, band.max_score))
                validate_grade_coverage(self.grading_scale.maximum_score, bands)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.label
