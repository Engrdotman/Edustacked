from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.academics.models import AcademicSession, ClassArm, ClassLevel
from apps.schools.models import School


MAX_STUDENT_PHOTO_SIZE = 2 * 1024 * 1024


def validate_student_photo_size(value):
    if value.size > MAX_STUDENT_PHOTO_SIZE:
        raise ValidationError("Student photos must be 2 MB or smaller.")


def student_photo_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"student-photos/{instance.school_id}/{uuid4().hex}{extension}"


class Student(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="students")
    admission_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=24, choices=Gender.choices, blank=True)
    photo = models.ImageField(
        upload_to=student_photo_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_student_photo_size],
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    admission_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "admission_number")
        constraints = [
            models.UniqueConstraint(Lower("admission_number"), "school", name="student_school_admission_ci_uniq"),
            models.CheckConstraint(condition=~Q(admission_number=""), name="student_admission_number_not_blank"),
            models.CheckConstraint(condition=~Q(first_name=""), name="student_first_name_not_blank"),
            models.CheckConstraint(condition=~Q(last_name=""), name="student_last_name_not_blank"),
        ]
        indexes = [
            models.Index(fields=("school", "status", "last_name"), name="student_school_status_name_idx"),
        ]

    def clean(self):
        super().clean()
        if self.admission_number and self.admission_number != self.admission_number.strip():
            self.admission_number = self.admission_number.strip()
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and (previous.school_id != self.school_id or previous.admission_number != self.admission_number):
                raise ValidationError("A student's school and admission number cannot be changed after admission.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.admission_number} — {self.first_name} {self.last_name}"


class Guardian(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="guardians")
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="guardian_profiles",
    )
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name", "id")
        indexes = [models.Index(fields=("school", "phone"), name="guardian_school_phone_idx")]

    def clean(self):
        super().clean()
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.school_id != self.school_id:
                raise ValidationError({"school": "A guardian's school cannot be changed after creation."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class StudentGuardian(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_guardian_links")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="student_links")
    relationship_type = models.CharField(max_length=40)
    is_primary_contact = models.BooleanField(default=False)
    is_emergency_contact = models.BooleanField(default=False)
    can_receive_communications = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_primary_contact", "guardian__full_name")
        constraints = [
            models.UniqueConstraint(fields=("student", "guardian"), name="student_guardian_pair_uniq"),
            models.UniqueConstraint(fields=("student",), condition=Q(is_primary_contact=True, is_active=True), name="student_one_primary_guardian_uniq"),
        ]

    def clean(self):
        super().clean()
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and any(getattr(previous, field) != getattr(self, field) for field in ("school_id", "student_id", "guardian_id")):
                raise ValidationError("A student-guardian relationship cannot be moved to another record or school.")
        if self.student_id and self.school_id and self.student.school_id != self.school_id:
            raise ValidationError({"student": "The student belongs to another school."})
        if self.guardian_id and self.school_id and self.guardian.school_id != self.school_id:
            raise ValidationError({"guardian": "The guardian belongs to another school."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class StudentEnrollment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        WITHDRAWN = "withdrawn", "Withdrawn"
        TRANSFERRED = "transferred", "Transferred"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_enrollments")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="student_enrollments")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="student_enrollments")
    class_arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="student_enrollments")
    enrollment_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    withdrawal_date = models.DateField(null=True, blank=True)
    withdrawal_reason = models.CharField(max_length=300, blank=True)
    transfer_date = models.DateField(null=True, blank=True)
    transfer_reason = models.CharField(max_length=300, blank=True)
    previous_enrollment = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="successor_enrollment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-enrollment_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "academic_session"),
                condition=Q(status__in=("pending", "active")),
                name="student_one_current_enrollment_per_session_uniq",
            ),
            models.CheckConstraint(
                condition=Q(withdrawal_date__isnull=True) | Q(withdrawal_date__gte=F("enrollment_date")),
                name="enrollment_withdrawal_after_start_ck",
            ),
            models.CheckConstraint(
                condition=Q(transfer_date__isnull=True) | Q(transfer_date__gte=F("enrollment_date")),
                name="enrollment_transfer_after_start_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("school", "academic_session", "status"), name="enroll_school_sess_st_idx"),
            models.Index(fields=("school", "class_level", "class_arm", "status"), name="enroll_school_class_arm_idx"),
        ]

    def clean(self):
        super().clean()
        parents = (
            ("student", self.student_id, self.student),
            ("academic_session", self.academic_session_id, self.academic_session),
            ("class_level", self.class_level_id, self.class_level),
            ("class_arm", self.class_arm_id, self.class_arm),
        )
        for field, object_id, obj in parents:
            if object_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field.replace('_', ' ')} belongs to another school."})
        if self.class_arm_id and self.class_level_id and self.class_arm.class_level_id != self.class_level_id:
            raise ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if self.class_level_id and not self.class_level.is_active:
            raise ValidationError({"class_level": "Students can only be enrolled in an active class."})
        if self.class_arm_id and not self.class_arm.is_active:
            raise ValidationError({"class_arm": "Students can only be enrolled in an active class arm."})
        if self.academic_session_id:
            if self.academic_session.status == AcademicSession.Status.COMPLETED:
                raise ValidationError({"academic_session": "Students cannot be enrolled in a completed session."})
            if self.enrollment_date < self.academic_session.start_date or self.enrollment_date > self.academic_session.end_date:
                raise ValidationError({"enrollment_date": "Enrollment date must fall within the academic session."})
            if self.status == self.Status.ACTIVE and self.academic_session.status != AcademicSession.Status.ACTIVE:
                raise ValidationError({"status": "An active enrollment requires an active academic session."})
        if self.student_id and self.student.status != Student.Status.ACTIVE:
            raise ValidationError({"student": "An inactive student cannot be enrolled."})
        if self.status == self.Status.WITHDRAWN and not self.withdrawal_date:
            raise ValidationError({"withdrawal_date": "A withdrawal date is required."})
        if self.status == self.Status.TRANSFERRED and (not self.transfer_date or not self.transfer_reason.strip()):
            raise ValidationError({"transfer_reason": "A transfer date and reason are required."})
        if self.status == self.Status.COMPLETED and self.academic_session_id and self.academic_session.status != AcademicSession.Status.COMPLETED:
            raise ValidationError({"status": "An enrollment can be completed only after its academic session is completed."})

        if self.previous_enrollment_id:
            previous = self.previous_enrollment
            if previous.student_id != self.student_id or previous.academic_session_id != self.academic_session_id or previous.school_id != self.school_id:
                raise ValidationError({"previous_enrollment": "A transfer must continue the same student's session and school."})
            if previous.status != self.Status.TRANSFERRED or previous.transfer_date != self.enrollment_date:
                raise ValidationError({"previous_enrollment": "A transfer must continue from a recorded transfer on the same date."})
        elif not self.pk and self.student_id and self.academic_session_id:
            existing = type(self).objects.filter(student_id=self.student_id, academic_session_id=self.academic_session_id).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({"academic_session": "This student already has an enrollment history for this session. Use the transfer workflow to change class or arm."})

        if not self.pk:
            if self.status not in (self.Status.PENDING, self.Status.ACTIVE):
                raise ValidationError({"status": "New enrollment records must start as pending or active."})
            return
        previous_state = type(self).objects.filter(pk=self.pk).first()
        if not previous_state:
            return
        immutable_fields = ("school_id", "student_id", "academic_session_id", "class_level_id", "class_arm_id", "enrollment_date", "previous_enrollment_id")
        changed = any(getattr(previous_state, field) != getattr(self, field) for field in immutable_fields)
        if previous_state.status in (self.Status.COMPLETED, self.Status.WITHDRAWN, self.Status.TRANSFERRED):
            if changed or self.status != previous_state.status:
                raise ValidationError("Historical enrollment records are immutable.")
        elif changed:
            raise ValidationError("Change class or arm using the transfer workflow; enrollment placement is immutable.")
        transitions = {
            self.Status.PENDING: {self.Status.PENDING, self.Status.ACTIVE, self.Status.WITHDRAWN},
            self.Status.ACTIVE: {self.Status.ACTIVE, self.Status.COMPLETED, self.Status.WITHDRAWN, self.Status.TRANSFERRED},
        }
        if self.status not in transitions.get(previous_state.status, set()):
            raise ValidationError({"status": "This enrollment status transition is not allowed."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} — {self.academic_session} — {self.class_level}/{self.class_arm}"
