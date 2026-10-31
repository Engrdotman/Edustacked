from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.students.models import StudentEnrollment

from .models import AssessmentPlan, AssessmentResult

CENT = Decimal("0.01")


def rounded(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def grading_snapshot(scale):
    return {
        "scale_id": scale.pk,
        "name": scale.name,
        "maximum_score": str(scale.maximum_score),
        "bands": [
            {"label": band.label, "description": band.description, "min_score": str(band.min_score), "max_score": str(band.max_score), "grade_point": str(band.grade_point) if band.grade_point is not None else None}
            for band in scale.bands.filter(is_active=True).order_by("min_score", "max_score")
        ],
    }


def eligible_enrollments(plan):
    term_start, term_end = plan.term.start_date, plan.term.end_date
    return StudentEnrollment.objects.filter(
        school=plan.school, academic_session=plan.academic_session,
        class_level=plan.class_level, class_arm=plan.class_arm,
        enrollment_date__lte=term_end,
    ).filter(
        Q(status__in=(StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED))
        | Q(status=StudentEnrollment.Status.WITHDRAWN, withdrawal_date__gte=term_start)
        | Q(status=StudentEnrollment.Status.TRANSFERRED, transfer_date__gte=term_start)
    ).select_related("student").order_by("student__last_name", "student__first_name")


def calculate_result(result, persist_approved_snapshot=False):
    plan = result.plan
    components = list(plan.components.select_related("component").order_by("position", "id"))
    scores = {entry.plan_component_id: entry for entry in result.scores.select_related("plan_component")}
    raw_total = Decimal("0")
    raw_maximum = Decimal("0")
    weighted_total = Decimal("0")
    rows = []
    complete = bool(components)
    for component in components:
        score = scores.get(component.pk)
        raw_maximum += component.max_score
        if score is None:
            complete = False
            rows.append({"plan_component_id": component.pk, "name": component.component.name, "score": None, "max_score": str(component.max_score), "weight": str(component.weight) if component.weight is not None else None})
            continue
        raw_total += score.score
        if component.weight is not None:
            weighted_total += (score.score / component.max_score) * component.weight
        rows.append({"plan_component_id": component.pk, "name": component.component.name, "score": str(score.score), "max_score": str(component.max_score), "weight": str(component.weight) if component.weight is not None else None})

    raw_total, raw_maximum = rounded(raw_total), rounded(raw_maximum)
    if plan.calculation_method == AssessmentPlan.CalculationMethod.WEIGHTED:
        grade_maximum = Decimal(plan.grading_scale_snapshot["maximum_score"])
        grade_total = rounded(weighted_total * grade_maximum / Decimal("100.00"))
    else:
        grade_total, grade_maximum = raw_total, raw_maximum
    percentage = rounded(grade_total * Decimal("100") / grade_maximum) if complete and grade_maximum else None
    grade_label, grade_point = "", None
    if complete and percentage is not None:
        # A grading scale is snapshotted onto the plan; convert the calculated result to that scale's range.
        scaled_score = rounded((grade_total * Decimal(plan.grading_scale_snapshot["maximum_score"])) / grade_maximum)
        for band in plan.grading_scale_snapshot.get("bands", []):
            if Decimal(band["min_score"]) <= scaled_score <= Decimal(band["max_score"]):
                grade_label = band["label"]
                grade_point = Decimal(band["grade_point"]) if band["grade_point"] is not None else None
                break
    payload = {
        "complete": complete, "components": rows,
        "component_total": str(raw_total), "component_maximum": str(raw_maximum),
        "calculated_total": str(grade_total) if complete else None,
        "calculated_maximum": str(grade_maximum) if complete else None,
        "percentage": str(percentage) if percentage is not None else None,
        "grade": grade_label, "grade_point": str(grade_point) if grade_point is not None else None,
    }
    if persist_approved_snapshot and complete:
        result.approved_total = grade_total
        result.approved_maximum = grade_maximum
        result.approved_percentage = percentage
        result.approved_grade = grade_label
        result.approved_grade_point = grade_point
        result.approved_calculation = payload
    return payload


def validate_plan_configuration(plan):
    components = list(plan.components.all())
    if not components:
        raise ValidationError({"components": "Add at least one component before publishing."})
    maximum = sum((item.max_score for item in components), Decimal("0"))
    scale_maximum = Decimal(plan.grading_scale_snapshot["maximum_score"])
    if plan.calculation_method == AssessmentPlan.CalculationMethod.RAW:
        if maximum != scale_maximum:
            raise ValidationError({"components": f"Raw component maxima must add to the grading scale maximum ({scale_maximum})."})
        if any(item.weight is not None for item in components):
            raise ValidationError({"components": "Raw score plans do not use weights."})
    else:
        if any(item.weight is None for item in components):
            raise ValidationError({"components": "Every weighted component needs a weight."})
        total_weight = sum((item.weight for item in components), Decimal("0"))
        if total_weight != Decimal("100.00"):
            raise ValidationError({"components": "Weighted component weights must total exactly 100.00%."})
