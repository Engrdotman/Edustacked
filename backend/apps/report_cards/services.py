from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import ClassSubject
from apps.attendance.services import finalized_enrollment_summary
from apps.results.models import AssessmentPlan, AssessmentResult
from apps.students.models import StudentEnrollment

from .models import ReportCard, ReportCardAuditEvent, ReportCardRevision


def report_enrollments(school, session, term, class_level, class_arm):
    return StudentEnrollment.objects.filter(
        school=school, academic_session=session, class_level=class_level, class_arm=class_arm,
        enrollment_date__lte=term.end_date,
    ).filter(
        Q(status__in=(StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED))
        | Q(status=StudentEnrollment.Status.WITHDRAWN, withdrawal_date__gte=term.start_date)
        | Q(status=StudentEnrollment.Status.TRANSFERRED, transfer_date__gte=term.start_date)
    ).select_related("student", "school", "academic_session", "class_level", "class_arm")


def attendance_summary(enrollment, term):
    return finalized_enrollment_summary(enrollment, term.start_date, term.end_date)


def _subject_data(enrollment, subject, plans):
    subject_plans = plans.get(subject.pk, [])
    if not subject_plans:
        return None, f"No assessment plan exists for {subject.name}."
    approved = []
    for plan in subject_plans:
        result = AssessmentResult.objects.filter(
            school=enrollment.school, plan=plan, student=enrollment.student,
            enrollment=enrollment, status=AssessmentResult.Status.APPROVED,
        ).prefetch_related("scores__plan_component__component").first()
        if result:
            approved.append((plan, result))
    if not approved:
        return None, f"No approved result exists for {subject.name}."
    if len(approved) > 1:
        return None, f"More than one approved assessment plan exists for {subject.name}; term-level aggregation is not configured."
    plan, result = approved[0]
    if not result.approved_calculation or result.approved_percentage is None or not result.approved_grade:
        return None, f"The approved result for {subject.name} is missing its saved calculation snapshot."
    calculation = result.approved_calculation
    return {
        "subject_id": subject.pk,
        "subject_name": subject.name,
        "assessment_plan_id": plan.pk,
        "assessment_plan_name": plan.name,
        "result_id": result.pk,
        "approved_result_version": result.version,
        "components": calculation.get("components", []),
        "total": str(result.approved_total),
        "maximum": str(result.approved_maximum),
        "percentage": str(result.approved_percentage),
        "grade": result.approved_grade,
        "grade_point": str(result.approved_grade_point) if result.approved_grade_point is not None else None,
        "grade_description": next((band.get("description") or band.get("label") for band in plan.grading_scale_snapshot.get("bands", []) if band.get("label") == result.approved_grade), result.approved_grade),
        "grading_scale_snapshot": plan.grading_scale_snapshot,
    }, None


def build_report_snapshot(enrollment, term):
    school = enrollment.school
    if term.school_id != enrollment.school_id or term.academic_session_id != enrollment.academic_session_id:
        raise ValidationError("A term is required from this enrollment's school and session.")
    class_subjects = list(ClassSubject.objects.filter(
        school=school, class_level=enrollment.class_level, is_active=True,
        subject__is_active=True,
    ).select_related("subject").order_by("subject__name"))
    errors = []
    if not class_subjects:
        errors.append("No active subjects are assigned to this class.")
    subjects = [entry.subject for entry in class_subjects]
    plans = {}
    for plan in AssessmentPlan.objects.filter(
            school=school, academic_session=enrollment.academic_session, term=term,
            class_level=enrollment.class_level, class_arm=enrollment.class_arm,
            subject__in=subjects, status__in=(AssessmentPlan.Status.PUBLISHED, AssessmentPlan.Status.CLOSED),
        ).select_related("subject").prefetch_related("results").order_by("subject_id", "-created_at"):
        plans.setdefault(plan.subject_id, []).append(plan)
    rows = []
    for subject in subjects:
        row, error = _subject_data(enrollment, subject, plans)
        if row:
            rows.append(row)
        if error:
            errors.append(error)
    school_settings = getattr(school, "settings", None)
    snapshot = {
        "school": {
            "name": school.name, "contact_email": school.contact_email,
            "contact_phone": school.contact_phone, "address": school.address,
            "state": school.state, "local_government_area": school.local_government_area,
            "website": school.website, "motto": school.motto, "description": school.description,
            "logo_path": school.logo.name if school.logo else "",
            "primary_color": school_settings.branding_primary_color if school_settings else "#285744",
        },
        "academic": {"session": enrollment.academic_session.name, "term": term.name, "term_start": term.start_date.isoformat(), "term_end": term.end_date.isoformat()},
        "student": {
            "name": " ".join(x for x in (enrollment.student.first_name, enrollment.student.middle_name, enrollment.student.last_name) if x),
            "admission_number": enrollment.student.admission_number,
            "date_of_birth": enrollment.student.date_of_birth.isoformat() if enrollment.student.date_of_birth else "",
            "gender": enrollment.student.get_gender_display() if enrollment.student.gender else "",
            "class_name": enrollment.class_level.name, "arm_name": enrollment.class_arm.name,
        },
        "subjects": rows,
        "attendance": attendance_summary(enrollment, term),
        "overall": None,
        "remarks": {"teacher": "", "head_teacher": "", "conduct": "", "effort": ""},
        "signatures": {"class_teacher": "", "head_teacher": "", "signed": False},
    }
    return snapshot, errors


@transaction.atomic
def generate_report_card(enrollment, term, actor):
    if term.school_id != enrollment.school_id or term.academic_session_id != enrollment.academic_session_id:
        raise ValidationError("The selected term does not belong to this enrollment's school and session.")
    if enrollment.enrollment_date > term.end_date:
        raise ValidationError("The student was not enrolled by the end of this term.")
    snapshot, errors = build_report_snapshot(enrollment, term)
    card, created = ReportCard.objects.select_for_update().get_or_create(
        school=enrollment.school, student=enrollment.student, enrollment=enrollment,
        academic_session=enrollment.academic_session, term=term,
        defaults={
            "class_level": enrollment.class_level, "class_arm": enrollment.class_arm,
            "identifier": f"RC-{uuid4().hex[:12].upper()}", "created_by": actor,
        },
    )
    if card.status == ReportCard.Status.FINALIZED:
        return card, None, errors
    revision, _ = ReportCardRevision.objects.get_or_create(
        report_card=card, revision_number=card.current_revision,
        defaults={"snapshot": snapshot, "validation_errors": errors, "generated_by": actor},
    )
    if not created and revision.status in (ReportCardRevision.Status.DRAFT, ReportCardRevision.Status.RETURNED):
        revision.snapshot = snapshot
        revision.validation_errors = errors
        revision.generated_by = actor
        revision.status = ReportCardRevision.Status.DRAFT
        revision.reason = ""
        revision.save(update_fields=("snapshot", "validation_errors", "generated_by", "status", "reason"))
    if created:
        ReportCardAuditEvent.objects.create(report_card=card, revision=revision, actor=actor, action="generated", metadata={"validation_error_count": len(errors)})
    return card, revision, errors


def validate_revision_ready(revision, card=None):
    snapshot = revision.snapshot
    errors = list(revision.validation_errors or [])
    if card is not None:
        fresh_snapshot, fresh_errors = build_report_snapshot(card.enrollment, card.term)
        source_fields = ("school", "academic", "student", "subjects", "attendance", "overall")
        if fresh_errors or any(fresh_snapshot.get(field) != snapshot.get(field) for field in source_fields):
            errors.append("Approved results, enrollment details, school configuration, or finalized attendance changed after generation. Regenerate this draft for review.")
    if not snapshot.get("subjects"):
        errors.append("At least one approved subject result is required.")
    for subject in snapshot.get("subjects", []):
        if not subject.get("total") or not subject.get("percentage") or not subject.get("grade"):
            errors.append(f"The saved result for {subject.get('subject_name', 'a subject')} is incomplete.")
    if errors:
        raise ValidationError({"validation_errors": errors})
    return True


@transaction.atomic
def finalize_report_card(card, actor, reason=""):
    """Single publication and credit-consumption boundary."""
    from apps.billing.services import finalize_report_card_with_credit

    return finalize_report_card_with_credit(card, actor, reason)


@transaction.atomic
def start_correction_revision(card, actor, reason):
    card = ReportCard.objects.select_for_update().get(pk=card.pk)
    if card.status != ReportCard.Status.FINALIZED:
        raise ValidationError({"status": "Only a finalized report card can start a correction revision."})
    if not reason.strip():
        raise ValidationError({"reason": "A correction reason is required."})
    previous = card.revisions.get(revision_number=card.current_revision, status=ReportCardRevision.Status.FINALIZED)
    enrollment = card.enrollment
    snapshot, errors = build_report_snapshot(enrollment, card.term)
    new_revision_number = card.current_revision + 1
    revision = ReportCardRevision.objects.create(
        report_card=card, revision_number=new_revision_number, status=ReportCardRevision.Status.DRAFT,
        snapshot=snapshot, validation_errors=errors, reason=reason, generated_by=actor,
    )
    card.current_revision = new_revision_number
    card.status = ReportCard.Status.DRAFT
    card.finalized_by = None
    card.finalized_at = None
    card.save(update_fields=("current_revision", "status", "finalized_by", "finalized_at", "updated_at"))
    ReportCardAuditEvent.objects.create(report_card=card, revision=previous, actor=actor, action="correction_revision_started", reason=reason, metadata={"new_revision": new_revision_number, "preserved_revision": previous.revision_number})
    return card, revision
