from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from django.utils import timezone

from apps.academics.models import AcademicSession
from apps.students.models import StudentEnrollment


def local_school_date(school):
    try:
        zone_name = school.settings.time_zone
        return timezone.localdate(timezone=ZoneInfo(zone_name))
    except (AttributeError, ZoneInfoNotFoundError):
        return timezone.localdate()


def eligible_enrollments(school, academic_session, class_level, class_arm, attendance_date):
    """Return enrollment snapshots whose placement covers attendance_date.

    Transfer effective dates begin the successor placement, so the old
    placement is eligible only through the preceding day. Withdrawal dates
    remain inclusive, and completed enrollments cover through the session end.
    """
    return StudentEnrollment.objects.filter(
        school=school,
        academic_session=academic_session,
        class_level=class_level,
        class_arm=class_arm,
        enrollment_date__lte=attendance_date,
    ).exclude(status=StudentEnrollment.Status.PENDING).filter(
        Q(status=StudentEnrollment.Status.ACTIVE)
        | Q(status=StudentEnrollment.Status.COMPLETED, academic_session__end_date__gte=attendance_date)
        | Q(status=StudentEnrollment.Status.WITHDRAWN, withdrawal_date__gte=attendance_date)
        | Q(status=StudentEnrollment.Status.TRANSFERRED, transfer_date__gt=attendance_date)
    ).select_related("student", "academic_session", "class_level", "class_arm")


def teacher_has_register_assignment(user, register):
    from apps.staff.models import TeacherAssignment, TeacherProfile
    return TeacherAssignment.objects.filter(
        school=register.school,
        teacher__staff__user=user,
        teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
        teacher__staff__status="active",
        academic_session=register.academic_session,
        class_level=register.class_level,
        class_arm=register.class_arm,
        status=TeacherAssignment.Status.ACTIVE,
        start_date__lte=register.attendance_date,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=register.attendance_date)).exists()


def scoped_teacher_register_filter(user):
    """Build a fail-closed filter for register views for an assigned teacher."""
    from apps.staff.models import TeacherAssignment, TeacherProfile
    query = Q(pk__in=[])
    assignments = TeacherAssignment.objects.filter(
        teacher__staff__user=user,
        teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
        teacher__staff__status="active",
        status=TeacherAssignment.Status.ACTIVE,
    )
    for assignment in assignments:
        item = Q(
            academic_session_id=assignment.academic_session_id,
            class_level_id=assignment.class_level_id,
            class_arm_id=assignment.class_arm_id,
            attendance_date__gte=assignment.start_date,
        )
        if assignment.end_date:
            item &= Q(attendance_date__lte=assignment.end_date)
        query |= item
    return query


def finalized_enrollment_summary(enrollment, start_date, end_date):
    """Return finalized attendance counts for one historical enrollment.

    Missing registers and unmarked records are excluded; only explicitly stored
    statuses contribute to the denominator.
    """
    from django.db.models import Count, Q

    from .models import AttendanceRecord, AttendanceRegister

    records = AttendanceRecord.objects.filter(
        school=enrollment.school, enrollment=enrollment,
        register__status=AttendanceRegister.Status.FINALIZED,
        register__attendance_date__gte=start_date,
        register__attendance_date__lte=end_date,
    ).exclude(status__isnull=True)
    counts = records.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
        late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
        excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    )
    total = counts["total"] or 0
    counts["attendance_percentage"] = round((counts["present"] + counts["late"]) * 100 / total, 2) if total else None
    counts["register_days_with_record"] = records.values("register__attendance_date").distinct().count()
    counts["policy"] = "Finalized attendance records only. Present and late count as attended; absent and excused are included in the denominator. Missing registers are excluded and are not treated as absences."
    return counts
