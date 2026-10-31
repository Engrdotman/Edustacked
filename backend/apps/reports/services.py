from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.attendance.models import AttendanceRecord, AttendanceRegister
from apps.billing.models import CreditAccount, CreditPayment, CreditTransaction, ReconciliationIssue
from apps.report_cards.models import ReportCard
from apps.results.models import AssessmentPlan, AssessmentResult
from apps.schools.models import SchoolMembership
from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
from apps.students.models import Student, StudentEnrollment

from .serializers import ReportFilterSerializer


def parse_report_filters(request, school):
    serializer = ReportFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    session_id = values.get("session")
    if session_id:
        session = AcademicSession.objects.filter(pk=session_id, school=school).first()
        if session is None:
            raise serializers.ValidationError({"session": "Choose an academic session in this school."})
    else:
        session = AcademicSession.objects.filter(school=school, status=AcademicSession.Status.ACTIVE).first()
    if session:
        values["session"] = session.pk
        values["session_name"] = session.name
    term_id = values.get("term")
    if term_id:
        term = Term.objects.filter(pk=term_id, school=school, academic_session_id=values.get("session")).first()
        if term is None:
            raise serializers.ValidationError({"term": "Choose a term in the selected school and session."})
    else:
        term = Term.objects.filter(school=school, academic_session_id=values.get("session"), status=Term.Status.ACTIVE).first() if session else None
    if term:
        values["term"] = term.pk
        values["term_name"] = term.name
    level_id = values.get("class_level")
    if level_id and not ClassLevel.objects.filter(pk=level_id, school=school).exists():
        raise serializers.ValidationError({"class_level": "Choose a class in this school."})
    arm_id = values.get("arm")
    arm_query = ClassArm.objects.filter(pk=arm_id, school=school)
    if level_id:
        arm_query = arm_query.filter(class_level_id=level_id)
    if arm_id and not arm_query.exists():
        raise serializers.ValidationError({"arm": "Choose an arm in the selected school and class."})

    today = timezone.localdate()
    start = values.get("start_date") or (term.start_date if term else today - timedelta(days=29))
    end = values.get("end_date") or (term.end_date if term and "end_date" not in values else today)
    if start > end:
        raise serializers.ValidationError({"start_date": "Start date must be on or before end date."})
    values.update({"start_date": start, "end_date": end})
    return values


def teacher_assignments(school, user, filters):
    return list(TeacherAssignment.objects.filter(
        school=school, teacher__staff__user=user,
        teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
        teacher__staff__status="active", status=TeacherAssignment.Status.ACTIVE,
    ).filter(
        Q(start_date__lte=filters["end_date"])
        & (Q(end_date__isnull=True) | Q(end_date__gte=filters["start_date"]))
    ).filter(
        **({"academic_session_id": filters["session"]} if filters.get("session") else {})
    ).values("academic_session_id", "class_level_id", "class_arm_id", "subject_id", "start_date", "end_date"))


def assignment_scope_q(assignments, *, include_subject=False):
    query = Q(pk__in=[])
    for item in assignments:
        scope = Q(academic_session_id=item["academic_session_id"], class_level_id=item["class_level_id"], class_arm_id=item["class_arm_id"])
        if include_subject:
            scope &= Q(subject_id=item["subject_id"])
        query |= scope
    return query


def selected_filter(queryset, filters, *, session_field="academic_session_id", term_field="term_id", class_field="class_level_id", arm_field="class_arm_id"):
    if filters.get("session"):
        queryset = queryset.filter(**{session_field: filters["session"]})
    if term_field and filters.get("term"):
        queryset = queryset.filter(**{term_field: filters["term"]})
    if filters.get("class_level"):
        queryset = queryset.filter(**{class_field: filters["class_level"]})
    if filters.get("arm"):
        queryset = queryset.filter(**{arm_field: filters["arm"]})
    return queryset


def date_filter(queryset, field, filters):
    return queryset.filter(**{
        f"{field}__gte": filters["start_date"],
        f"{field}__lte": filters["end_date"],
    })


def attendance_queryset(school, filters, assignments=None):
    rows = AttendanceRecord.objects.filter(
        school=school, register__school=school,
        register__status=AttendanceRegister.Status.FINALIZED,
        status__isnull=False,
        register__attendance_date__gte=filters["start_date"],
        register__attendance_date__lte=filters["end_date"],
    )
    rows = selected_filter(rows, filters, session_field="register__academic_session_id", term_field="register__term_id", class_field="register__class_level_id", arm_field="register__class_arm_id")
    if assignments is not None:
        scope = Q(pk__in=[])
        for item in assignments:
            scope |= Q(
                register__academic_session_id=item["academic_session_id"],
                register__class_level_id=item["class_level_id"],
                register__class_arm_id=item["class_arm_id"],
                register__attendance_date__gte=max(filters["start_date"], item["start_date"]),
            ) & (Q(register__attendance_date__lte=item["end_date"]) if item["end_date"] else Q())
        rows = rows.filter(scope)
    return rows


def attendance_summary(rows):
    values = rows.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
        late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
        excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    )
    total = values["total"] or 0
    values["attendance_percentage"] = round(((values["present"] + values["late"]) * 100 / total), 2) if total else None
    values["has_records"] = bool(total)
    values["policy"] = "Finalized registers and explicitly marked records only. Present and late count as attended; absent and excused are included in the denominator. Missing registers and unmarked records are excluded."
    return values


def dashboard_metrics(school, user, role, filters, permissions):
    data = {"session": {"id": filters.get("session"), "name": filters.get("session_name")},
            "term": {"id": filters.get("term"), "name": filters.get("term_name")},
            "date_range": {"start": filters["start_date"], "end": filters["end_date"]},
            "available_sections": [], "metrics": {}, "filters": {"sessions": [], "terms": [], "classes": [], "arms": []}}
    if "staff.view" in permissions:
        staff = StaffProfile.objects.filter(school=school, status=StaffProfile.Status.ACTIVE)
        data["metrics"]["active_staff"] = staff.count()
    enrollments = StudentEnrollment.objects.filter(school=school)
    if filters.get("session"):
        enrollments = enrollments.filter(academic_session_id=filters["session"])
    if role == "teacher":
        assignments = teacher_assignments(school, user, filters)
        scope = Q(pk__in=[])
        for row in assignments:
            scope |= Q(academic_session_id=row["academic_session_id"], class_level_id=row["class_level_id"], class_arm_id=row["class_arm_id"])
        enrollments = enrollments.filter(scope)
    if filters.get("class_level"):
        enrollments = enrollments.filter(class_level_id=filters["class_level"])
    if filters.get("arm"):
        enrollments = enrollments.filter(class_arm_id=filters["arm"])
    if "reports.enrollment" in permissions or role == SchoolMembership.Role.TEACHER:
        data["metrics"]["currently_enrolled"] = enrollments.filter(status=StudentEnrollment.Status.ACTIVE, student__status=Student.Status.ACTIVE).count()
    if "reports.enrollment" in permissions:
        data["available_sections"].append("enrollment")
        data["metrics"]["new_admissions"] = Student.objects.filter(school=school, admission_date__gte=filters["start_date"], admission_date__lte=filters["end_date"]).count()
    if "reports.attendance" in permissions:
        data["available_sections"].append("attendance")
        rows = attendance_queryset(school, filters, teacher_assignments(school, user, filters) if role == "teacher" else None)
        data["metrics"]["attendance"] = attendance_summary(rows)
    if "reports.academics" in permissions:
        data["available_sections"].append("academics")
        plans = selected_filter(AssessmentPlan.objects.filter(school=school), filters)
        if role == "teacher":
            plans = plans.filter(assignment_scope_q(teacher_assignments(school, user, filters), include_subject=True))
        result_counts = AssessmentResult.objects.filter(school=school, plan__in=plans).aggregate(
            approved=Count("id", filter=Q(status=AssessmentResult.Status.APPROVED)),
            submitted=Count("id", filter=Q(status=AssessmentResult.Status.SUBMITTED)),
            draft=Count("id", filter=Q(status=AssessmentResult.Status.DRAFT)),
            average_approved_percentage=Avg("approved_percentage", filter=Q(status=AssessmentResult.Status.APPROVED)),
        )
        result_counts["average_approved_percentage"] = round(float(result_counts["average_approved_percentage"]), 2) if result_counts["average_approved_percentage"] is not None else None
        data["metrics"]["results"] = result_counts
        data["metrics"]["class_performance"] = [
            {"class_name": row["plan__class_level__name"], "average_percentage": round(float(row["average"]), 2)}
            for row in AssessmentResult.objects.filter(
                school=school, plan__in=plans, status=AssessmentResult.Status.APPROVED,
            ).values("plan__class_level__name").annotate(average=Avg("approved_percentage")).order_by("plan__class_level__name")
        ]
    if "reports.report_cards" in permissions:
        data["available_sections"].append("report_cards")
        cards = selected_filter(ReportCard.objects.filter(school=school), filters)
        if role == "teacher":
            cards = cards.filter(assignment_scope_q(teacher_assignments(school, user, filters)))
        data["metrics"]["report_cards"] = {status: cards.filter(status=status).count() for status, _ in ReportCard.Status.choices}
        data["metrics"]["report_cards"]["published"] = data["metrics"]["report_cards"].pop(ReportCard.Status.FINALIZED)
    if "reports.finance" in permissions:
        data["available_sections"].append("finance")
        account = CreditAccount.objects.filter(school=school).first()
        data["metrics"]["credit_balance"] = account.balance if account else None
    if role != SchoolMembership.Role.ACCOUNTANT:
        sessions = AcademicSession.objects.filter(school=school)
        assigned_rows = teacher_assignments(school, user, filters) if role == SchoolMembership.Role.TEACHER else None
        if assigned_rows is not None:
            sessions = sessions.filter(pk__in={row["academic_session_id"] for row in assigned_rows})
        data["filters"]["sessions"] = list(sessions.values("id", "name", "status", "start_date", "end_date"))
        session_ids = list(sessions.values_list("id", flat=True))
        terms = Term.objects.filter(school=school, academic_session_id__in=session_ids)
        data["filters"]["terms"] = list(terms.values("id", "name", "academic_session_id", "status", "start_date", "end_date"))
        classes = ClassLevel.objects.filter(school=school)
        arms = ClassArm.objects.filter(school=school)
        if assigned_rows is not None:
            class_ids = {row["class_level_id"] for row in assigned_rows}
            arm_ids = {row["class_arm_id"] for row in assigned_rows}
            classes, arms = classes.filter(pk__in=class_ids), arms.filter(pk__in=arm_ids)
        data["filters"]["classes"] = list(classes.values("id", "name"))
        data["filters"]["arms"] = list(arms.values("id", "name", "class_level_id"))
    return data


def enrollment_report(school, filters, *, include_students=False):
    rows = selected_filter(StudentEnrollment.objects.filter(school=school).exclude(status=StudentEnrollment.Status.PENDING).select_related(
        "student", "academic_session", "class_level", "class_arm"
    ), filters, term_field=None)
    distribution = list(rows.values(
        "class_level_id", "class_level__name", "class_arm_id", "class_arm__name", "status"
    ).annotate(count=Count("id")).order_by("class_level__name", "class_arm__name", "status"))
    outcome = rows.aggregate(
        withdrawn=Count("id", filter=Q(status=StudentEnrollment.Status.WITHDRAWN, withdrawal_date__gte=filters["start_date"], withdrawal_date__lte=filters["end_date"])),
        transferred=Count("id", filter=Q(status=StudentEnrollment.Status.TRANSFERRED, transfer_date__gte=filters["start_date"], transfer_date__lte=filters["end_date"])),
    )
    admission_count = Student.objects.filter(school=school, admission_date__gte=filters["start_date"], admission_date__lte=filters["end_date"]).count()
    result = {"session": filters.get("session_name"), "date_range": {"start": filters["start_date"], "end": filters["end_date"]},
              "admissions": admission_count, "outcomes": outcome, "distribution": distribution}
    if include_students:
        result["students"] = rows.order_by("student__last_name", "student__first_name", "id")
    return result


def attendance_report(school, filters, assignments=None, *, by_student=False):
    rows = attendance_queryset(school, filters, assignments)
    if by_student:
        search = filters.get("search", "").strip()
        if search:
            rows = rows.filter(Q(student__first_name__icontains=search) | Q(student__middle_name__icontains=search) | Q(student__last_name__icontains=search) | Q(student__admission_number__icontains=search))
        return rows.values("student_id", "student__first_name", "student__middle_name", "student__last_name", "student__admission_number", "register__academic_session__name", "register__class_level__name", "register__class_arm__name").annotate(
            total=Count("id"), present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)), late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
            excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
        ).order_by("student__last_name", "student__first_name")
    return list(rows.values("register__attendance_date", "register__class_level_id", "register__class_level__name", "register__class_arm_id", "register__class_arm__name").annotate(
        total=Count("id"), present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)), late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
        excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    ).order_by("register__attendance_date", "register__class_level__name", "register__class_arm__name"))


def academic_report(school, filters, assignments=None):
    plans = selected_filter(AssessmentPlan.objects.filter(school=school).select_related("class_level", "class_arm", "subject", "academic_session", "term"), filters)
    if assignments is not None:
        scope = Q(pk__in=[])
        for item in assignments:
            item_scope = Q(academic_session_id=item["academic_session_id"], class_level_id=item["class_level_id"], class_arm_id=item["class_arm_id"], subject_id=item["subject_id"], term__end_date__gte=item["start_date"])
            if item["end_date"]:
                item_scope &= Q(term__start_date__lte=item["end_date"])
            scope |= item_scope
        plans = plans.filter(scope)
    aggregates = plans.annotate(
        approved=Count("results", filter=Q(results__status=AssessmentResult.Status.APPROVED)),
        submitted=Count("results", filter=Q(results__status=AssessmentResult.Status.SUBMITTED)),
        draft=Count("results", filter=Q(results__status=AssessmentResult.Status.DRAFT)),
        average_percentage=Avg("results__approved_percentage", filter=Q(results__status=AssessmentResult.Status.APPROVED)),
    ).order_by("class_level__name", "class_arm__name", "subject__name")
    grade_rows = AssessmentResult.objects.filter(school=school, plan__in=plans, status=AssessmentResult.Status.APPROVED).values("plan_id", "approved_grade").annotate(count=Count("id")).order_by("plan_id", "approved_grade")
    grades_by_plan = {}
    for row in grade_rows:
        grades_by_plan.setdefault(row["plan_id"], []).append({"approved_grade": row["approved_grade"], "count": row["count"]})
    result = []
    for plan in aggregates:
        result.append({"plan_id": plan.pk, "session": plan.academic_session.name, "term": plan.term.name,
                       "class_name": plan.class_level.name, "arm_name": plan.class_arm.name, "subject": plan.subject.name,
                       "plan_status": plan.status, "approved": plan.approved, "submitted": plan.submitted, "draft": plan.draft,
                       "average_approved_percentage": round(float(plan.average_percentage), 2) if plan.average_percentage is not None else None,
                       "grade_distribution": grades_by_plan.get(plan.pk, [])})
    return result


def report_card_report(school, filters, assignments=None):
    cards = selected_filter(ReportCard.objects.filter(school=school), filters)
    cohort = selected_filter(StudentEnrollment.objects.filter(school=school).exclude(status=StudentEnrollment.Status.PENDING), filters, term_field=None)
    if assignments is not None:
        scope = Q(pk__in=[])
        for item in assignments:
            item_scope = Q(academic_session_id=item["academic_session_id"], class_level_id=item["class_level_id"], class_arm_id=item["class_arm_id"], term__end_date__gte=item["start_date"])
            if item["end_date"]:
                item_scope &= Q(term__start_date__lte=item["end_date"])
            scope |= item_scope
        cards, cohort = cards.filter(scope), cohort.filter(scope)
    counts = list(cards.values("class_level_id", "class_level__name", "class_arm_id", "class_arm__name").annotate(
        draft=Count("id", filter=Q(status=ReportCard.Status.DRAFT)), review=Count("id", filter=Q(status=ReportCard.Status.REVIEW)),
        approved=Count("id", filter=Q(status=ReportCard.Status.APPROVED)), published=Count("id", filter=Q(status=ReportCard.Status.FINALIZED)),
        total=Count("id"),
    ).order_by("class_level__name", "class_arm__name"))
    expected_rows = list(cohort.values("class_level_id", "class_level__name", "class_arm_id", "class_arm__name").annotate(expected=Count("id")))
    by_key = {(row["class_level_id"], row["class_arm_id"]): row for row in counts}
    cohort_by_key = {(row["class_level_id"], row["class_arm_id"]): row for row in expected_rows}
    merged = []
    for key in set(by_key) | set(cohort_by_key):
        row = by_key.get(key, {"class_level_id": key[0], "class_arm_id": key[1], "draft": 0, "review": 0, "approved": 0, "published": 0, "total": 0})
        cohort_row = cohort_by_key.get(key, {})
        row["class_level__name"] = row.get("class_level__name") or cohort_row.get("class_level__name")
        row["class_arm__name"] = row.get("class_arm__name") or cohort_row.get("class_arm__name")
        row["expected_students"] = cohort_row.get("expected", 0)
        row["publication_percentage"] = round(row["published"] * 100 / row["expected_students"], 2) if row["expected_students"] else None
        row["class_name"] = row.pop("class_level__name")
        row["arm_name"] = row.pop("class_arm__name")
        merged.append(row)
    merged.sort(key=lambda row: (row["class_name"], row["arm_name"]))
    status_counts = {status: cards.filter(status=status).count() for status, _ in ReportCard.Status.choices}
    status_counts["published"] = status_counts.pop(ReportCard.Status.FINALIZED)
    return {"statuses": status_counts, "classes": merged}


def finance_report(school, filters):
    payments = CreditPayment.objects.filter(school=school, created_at__date__gte=filters["start_date"], created_at__date__lte=filters["end_date"])
    by_status = list(payments.values("status", "currency").annotate(count=Count("id"), amount_minor=Sum("amount_minor"), credits=Sum("credits")).order_by("status", "currency"))
    successful = payments.filter(status=CreditPayment.Status.SUCCESS)
    transactions = list(CreditTransaction.objects.filter(school=school, created_at__date__gte=filters["start_date"], created_at__date__lte=filters["end_date"]).values("kind").annotate(count=Count("id"), credit_change=Sum("amount")).order_by("kind"))
    issues = ReconciliationIssue.objects.filter(school=school, created_at__date__gte=filters["start_date"], created_at__date__lte=filters["end_date"])
    account = CreditAccount.objects.filter(school=school).first()
    gross = successful.aggregate(total=Sum("amount_minor"))["total"] or 0
    return {"currency": "NGN", "credit_balance": account.balance if account else None,
            "successful_purchases": successful.count(), "gross_successful_purchases_ngn": round(gross / 100, 2),
            "payments_by_status": by_status, "ledger_by_kind": transactions,
            "reconciliation_issues": {"open": issues.filter(status=ReconciliationIssue.Status.OPEN).count(), "resolved": issues.filter(status=ReconciliationIssue.Status.RESOLVED).count()}}
