from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from datetime import timedelta

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.models import School
from apps.students.models import Student, StudentEnrollment


class AttendanceRegister(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        FINALIZED = "finalized", "Finalized"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="attendance_registers")
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="attendance_registers")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="attendance_registers")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="attendance_registers")
    class_arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="attendance_registers")
    attendance_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_attendance_registers")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="submitted_attendance_registers")
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="finalized_attendance_registers")
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reopened_attendance_registers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-attendance_date", "class_level__name", "class_arm__name")
        constraints = [
            models.UniqueConstraint(fields=("school", "class_level", "class_arm", "attendance_date"), name="att_register_class_day_uniq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="att_register_version_positive"),
        ]
        indexes = [models.Index(fields=("school", "attendance_date", "status"), name="att_register_school_day_idx"), models.Index(fields=("school", "academic_session", "class_level", "class_arm"), name="att_register_scope_idx")]

    def clean(self):
        super().clean()
        refs = (
            ("academic_session", self.academic_session_id, self.academic_session),
            ("term", self.term_id, self.term),
            ("class_level", self.class_level_id, self.class_level),
            ("class_arm", self.class_arm_id, self.class_arm),
        )
        for field, object_id, obj in refs:
            if object_id and self.school_id and obj.school_id != self.school_id:
                raise ValidationError({field: f"The selected {field.replace('_', ' ')} belongs to another school."})
        if self.class_arm_id and self.class_level_id and self.class_arm.class_level_id != self.class_level_id:
            raise ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if self.term_id and self.academic_session_id and self.term.academic_session_id != self.academic_session_id:
            raise ValidationError({"term": "The selected term does not belong to the selected session."})
        if self.attendance_date and self.academic_session_id:
            if self.attendance_date < self.academic_session.start_date or self.attendance_date > self.academic_session.end_date:
                raise ValidationError({"attendance_date": "Attendance date must fall within the academic session."})
        if self.attendance_date and self.term_id:
            if self.attendance_date < self.term.start_date or self.attendance_date > self.term.end_date:
                raise ValidationError({"attendance_date": "Attendance date must fall within the selected term."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous:
                immutable = ("school_id", "academic_session_id", "term_id", "class_level_id", "class_arm_id", "attendance_date", "created_by_id")
                if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                    raise ValidationError("Register identity cannot be changed after creation.")
                allowed = {
                    self.Status.DRAFT: {self.Status.DRAFT, self.Status.SUBMITTED},
                    self.Status.SUBMITTED: {self.Status.SUBMITTED, self.Status.FINALIZED},
                    self.Status.FINALIZED: {self.Status.FINALIZED, self.Status.SUBMITTED},
                }
                if self.status not in allowed[previous.status]:
                    raise ValidationError({"status": "This register status transition is not allowed."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance register history cannot be deleted.")

    def __str__(self):
        return f"{self.attendance_date} — {self.class_level}/{self.class_arm}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused absence"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="attendance_records")
    register = models.ForeignKey(AttendanceRegister, on_delete=models.PROTECT, related_name="records")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="attendance_records")
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="attendance_records")
    status = models.CharField(max_length=10, choices=Status.choices, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="recorded_attendance")
    last_modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="modified_attendance")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student__last_name", "student__first_name", "student__admission_number")
        constraints = [models.UniqueConstraint(fields=("register", "student"), name="att_register_student_uniq")]
        indexes = [models.Index(fields=("school", "student", "status"), name="att_school_student_status_idx"), models.Index(fields=("school", "register", "status"), name="att_school_register_status_idx")]

    def clean(self):
        super().clean()
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if previous and any(getattr(previous, field) != getattr(self, field) for field in ("school_id", "register_id", "student_id", "enrollment_id")):
            raise ValidationError("Attendance record identity cannot be changed after creation.")
        if self.register_id and self.school_id and self.register.school_id != self.school_id:
            raise ValidationError({"register": "The register belongs to another school."})
        if self.student_id and self.school_id and self.student.school_id != self.school_id:
            raise ValidationError({"student": "The student belongs to another school."})
        if self.enrollment_id and self.school_id and self.enrollment.school_id != self.school_id:
            raise ValidationError({"enrollment": "The enrollment belongs to another school."})
        if self.enrollment_id and self.register_id:
            register = self.register
            enrollment = self.enrollment
            if enrollment.student_id != self.student_id:
                raise ValidationError({"enrollment": "The enrollment does not belong to this student."})
            if enrollment.academic_session_id != register.academic_session_id or enrollment.class_level_id != register.class_level_id or enrollment.class_arm_id != register.class_arm_id:
                raise ValidationError({"enrollment": "The enrollment does not match the register's session, class, and arm."})
            if enrollment.status not in (StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED, StudentEnrollment.Status.WITHDRAWN, StudentEnrollment.Status.TRANSFERRED):
                raise ValidationError({"enrollment": "The student did not have an eligible enrollment on this date."})
            end_date = enrollment.withdrawal_date if enrollment.status == StudentEnrollment.Status.WITHDRAWN else enrollment.transfer_date - timedelta(days=1) if enrollment.status == StudentEnrollment.Status.TRANSFERRED and enrollment.transfer_date else register.academic_session.end_date
            if register.attendance_date < enrollment.enrollment_date or register.attendance_date > end_date:
                raise ValidationError({"enrollment": "The student was not enrolled in this class on the attendance date."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance history cannot be deleted.")


class AttendanceAuditEvent(models.Model):
    class EventType(models.TextChoices):
        RECORDED = "recorded", "Attendance recorded"
        CORRECTED = "corrected", "Attendance corrected"
        SUBMITTED = "submitted", "Register submitted"
        FINALIZED = "finalized", "Register finalized"
        REOPENED = "reopened", "Register reopened"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="attendance_audit_events")
    register = models.ForeignKey(AttendanceRegister, on_delete=models.PROTECT, related_name="audit_events")
    record = models.ForeignKey(AttendanceRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    event_type = models.CharField(max_length=12, choices=EventType.choices)
    previous_status = models.CharField(max_length=10, blank=True)
    new_status = models.CharField(max_length=10, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_audit_events")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("school", "register", "created_at"), name="att_audit_register_time_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Attendance audit events are immutable.")
        if self.register_id and self.register.school_id != self.school_id:
            raise ValidationError({"register": "The register belongs to another school."})
        if self.record_id and self.record.register_id != self.register_id:
            raise ValidationError({"record": "The record belongs to another register."})
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance audit history cannot be deleted.")
