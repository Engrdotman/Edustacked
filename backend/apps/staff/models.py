from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Subject
from apps.schools.models import School, SchoolMembership

MAX_STAFF_PHOTO_SIZE = 2 * 1024 * 1024


def validate_staff_photo_size(value):
    if value.size > MAX_STAFF_PHOTO_SIZE:
        raise ValidationError("Staff photos must be 2 MB or smaller.")


def staff_photo_upload_path(instance, filename):
    return f"staff-photos/{instance.school_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class StaffProfile(models.Model):
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"
        TEMPORARY = "temporary", "Temporary"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        FORMER = "former", "Former staff"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="staff_profiles")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_profiles")
    staff_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    work_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=120)
    department = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=12, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    employment_start_date = models.DateField()
    employment_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    photo = models.ImageField(upload_to=staff_photo_upload_path, blank=True, null=True, validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_staff_photo_size])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "staff_number")
        constraints = [
            models.UniqueConstraint(Lower("staff_number"), "school", name="staff_school_number_ci_uniq"),
            models.UniqueConstraint(fields=("school", "user"), condition=Q(user__isnull=False), name="staff_school_user_uniq"),
            models.CheckConstraint(condition=~Q(staff_number=""), name="staff_number_not_blank"),
            models.CheckConstraint(condition=Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=F("employment_start_date")), name="staff_employment_dates_ck"),
        ]
        indexes = [models.Index(fields=("school", "status", "last_name"), name="staff_school_status_nm_idx")]

    def clean(self):
        super().clean()
        if self.employment_start_date and self.employment_end_date and self.employment_end_date < self.employment_start_date:
            raise ValidationError({"employment_end_date": "Employment end date cannot be before the start date."})
        if self.status == self.Status.FORMER and not self.employment_end_date:
            raise ValidationError({"employment_end_date": "Former staff must have an employment end date."})
        if self.status in (self.Status.ACTIVE, self.Status.SUSPENDED) and self.employment_end_date:
            raise ValidationError({"employment_end_date": "Active or suspended staff cannot have an end date."})
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self.user_id and (not previous or previous.user_id != self.user_id):
            if not SchoolMembership.objects.filter(user_id=self.user_id, school_id=self.school_id, is_active=True).exists():
                raise ValidationError({"user": "The account must already have an active membership in this school. Linking does not grant access."})
        if previous:
            if previous.school_id != self.school_id or previous.staff_number != self.staff_number:
                raise ValidationError("A staff member's school and staff number cannot be changed.")
            if previous.status == self.Status.FORMER and self.status != self.Status.FORMER:
                raise ValidationError({"status": "Former staff records cannot be reactivated."})
            allowed = {
                self.Status.ACTIVE: {self.Status.ACTIVE, self.Status.INACTIVE, self.Status.SUSPENDED, self.Status.FORMER},
                self.Status.INACTIVE: {self.Status.INACTIVE, self.Status.ACTIVE, self.Status.FORMER},
                self.Status.SUSPENDED: {self.Status.SUSPENDED, self.Status.ACTIVE, self.Status.INACTIVE, self.Status.FORMER},
            }
            if self.status not in allowed.get(previous.status, {previous.status}):
                raise ValidationError({"status": "This employment status transition is not allowed."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff_number} — {self.first_name} {self.last_name}"


class TeacherProfile(models.Model):
    class TeachingStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_profiles")
    staff = models.OneToOneField(StaffProfile, on_delete=models.PROTECT, related_name="teacher_profile")
    qualification_summary = models.CharField(max_length=300, blank=True)
    specialization = models.CharField(max_length=150, blank=True)
    teaching_status = models.CharField(max_length=10, choices=TeachingStatus.choices, default=TeachingStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("school", "staff"), name="teacher_school_staff_uniq")]

    def clean(self):
        super().clean()
        if self.staff_id and self.school_id and self.staff.school_id != self.school_id:
            raise ValidationError({"staff": "The staff profile belongs to another school."})
        if self.staff_id and self.staff.status != StaffProfile.Status.ACTIVE and self.teaching_status == self.TeachingStatus.ACTIVE:
            raise ValidationError({"teaching_status": "Only active staff can be designated as an active teacher."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Teacher: {self.staff}"


class TeacherAssignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_assignments")
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name="assignments")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="teacher_assignments")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="teacher_assignments")
    class_arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="teacher_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="teacher_assignments")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    previous_assignment = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replacement_assignment")
    change_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_date", "teacher__staff__last_name")
        constraints = [
            models.UniqueConstraint(fields=("teacher", "academic_session", "class_level", "class_arm", "subject"), condition=Q(status="active"), name="teacher_assignment_active_uniq"),
            models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")), name="teacher_assignment_dates_ck"),
        ]
        indexes = [models.Index(fields=("school", "academic_session", "status"), name="teach_assign_school_sess_idx"), models.Index(fields=("school", "class_level", "class_arm", "subject"), name="teach_assign_class_subject_idx")]

    def clean(self):
        super().clean()
        for field, obj_id, obj in (
            ("teacher", self.teacher_id, self.teacher),
            ("academic_session", self.academic_session_id, self.academic_session),
            ("class_level", self.class_level_id, self.class_level),
            ("class_arm", self.class_arm_id, self.class_arm),
            ("subject", self.subject_id, self.subject),
        ):
            if obj_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field.replace('_', ' ')} belongs to another school."})
        if self.class_arm_id and self.class_level_id and self.class_arm.class_level_id != self.class_level_id:
            raise ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if self.class_level_id and self.subject_id:
            from apps.academics.models import ClassSubject
            if ClassSubject.objects.filter(class_level_id=self.class_level_id, is_active=True).exists() and not ClassSubject.objects.filter(class_level_id=self.class_level_id, subject_id=self.subject_id, is_active=True).exists():
                raise ValidationError({"subject": "The subject is not assigned to the selected class."})
        if self.class_level_id and not self.class_level.is_active:
            raise ValidationError({"class_level": "Assignments require an active class."})
        if self.class_arm_id and not self.class_arm.is_active:
            raise ValidationError({"class_arm": "Assignments require an active class arm."})
        if self.subject_id and not self.subject.is_active:
            raise ValidationError({"subject": "Assignments require an active subject."})
        if self.status == self.Status.ACTIVE and self.teacher_id and self.teacher.teaching_status != TeacherProfile.TeachingStatus.ACTIVE:
            raise ValidationError({"teacher": "Only an active teacher can receive an active assignment."})
        if self.status == self.Status.ACTIVE and self.teacher_id and self.teacher.staff.status != StaffProfile.Status.ACTIVE:
            raise ValidationError({"teacher": "Inactive, suspended, or former staff cannot receive active assignments."})
        if self.academic_session_id:
            session = self.academic_session
            if session.status == AcademicSession.Status.COMPLETED:
                raise ValidationError({"academic_session": "Assignments cannot be created for a completed session."})
            if self.start_date and (self.start_date < session.start_date or self.start_date > session.end_date):
                raise ValidationError({"start_date": "Assignment start date must fall within the academic session."})
            if self.end_date and self.end_date > session.end_date:
                raise ValidationError({"end_date": "Assignment end date cannot exceed the academic session."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Assignment end date cannot be before its start date."})
        if self.previous_assignment_id:
            old = self.previous_assignment
            if old.school_id != self.school_id or old.academic_session_id != self.academic_session_id or old.status != self.Status.ENDED:
                raise ValidationError({"previous_assignment": "A replacement must follow an ended assignment in the same school and session."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous:
                immutable = ("school_id", "teacher_id", "academic_session_id", "class_level_id", "class_arm_id", "subject_id", "start_date", "previous_assignment_id")
                if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                    raise ValidationError("Assignment details are immutable; end and replace the assignment to change them.")
                if previous.status in (self.Status.ENDED, self.Status.CANCELLED) and self.status != previous.status:
                    raise ValidationError("Ended and cancelled assignments cannot be reactivated.")
                if previous.status == self.Status.ACTIVE and self.status not in (self.Status.ACTIVE, self.Status.ENDED, self.Status.CANCELLED):
                    raise ValidationError({"status": "This assignment status transition is not allowed."})
        elif self.status != self.Status.ACTIVE:
            raise ValidationError({"status": "New assignments must start as active."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher} — {self.subject} — {self.class_level}/{self.class_arm}"
