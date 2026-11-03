import csv
from datetime import date
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q
from django.db.models.functions import TruncMonth
from django.http import StreamingHttpResponse
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.models import SchoolMembership
from apps.staff.models import TeacherAssignment

from .models import CbtResult, CbtResultCorrection, Examination, ExaminationAssignment, LocalCbtSyncEvent, Question
from .services import apply_result_correction
from .views import CbtSchoolViewMixin


def _teacher_assignments(view, school):
    if view.request.user.is_superuser:
        return None
    membership = SchoolMembership.objects.filter(user=view.request.user, school=school, is_active=True).first()
    if not membership or membership.role != SchoolMembership.Role.TEACHER:
        return None
    return TeacherAssignment.objects.filter(
        school=school, teacher__staff__user=view.request.user, status=TeacherAssignment.Status.ACTIVE,
    ).select_related("academic_session", "class_level", "class_arm", "subject")


def _teacher_exam_q(assignments):
    scope = Q(pk__in=[])
    for assignment in assignments:
        scope |= Q(
            academic_session_id=assignment.academic_session_id,
            class_level_id=assignment.class_level_id,
            subject_id=assignment.subject_id,
        )
    return scope


def _teacher_result_q(assignments):
    scope = Q(pk__in=[])
    for assignment in assignments:
        scope |= Q(
            examination__academic_session_id=assignment.academic_session_id,
            examination__class_level_id=assignment.class_level_id,
            examination__subject_id=assignment.subject_id,
            assignment__student__enrollments__school_id=assignment.school_id,
            assignment__student__enrollments__academic_session_id=assignment.academic_session_id,
            assignment__student__enrollments__class_level_id=assignment.class_level_id,
            assignment__student__enrollments__class_arm_id=assignment.class_arm_id,
        )
    return scope


def _teacher_assignment_q(assignments):
    scope = Q(pk__in=[])
    for assignment in assignments:
        scope |= Q(
            student__enrollments__school_id=assignment.school_id,
            student__enrollments__academic_session_id=assignment.academic_session_id,
            student__enrollments__class_level_id=assignment.class_level_id,
            student__enrollments__class_arm_id=assignment.class_arm_id,
        )
    return scope


class ResultPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CbtResultsBaseView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated,)
    required_school_permission = "cbt.results.view"

    def get_permissions(self):
        self.required_school_permission = "cbt.results.view" if self.request.method in {"GET", "HEAD", "OPTIONS"} else "cbt.results.manage"
        return super().get_permissions()

    def scoped_data(self):
        school = self.get_school()
        teacher_assignments = _teacher_assignments(self, school)
        exams = Examination.objects.filter(school=school).select_related("academic_session", "term", "class_level", "subject")
        results = CbtResult.objects.filter(school=school).select_related(
            "examination__academic_session", "examination__term", "examination__class_level",
            "examination__subject", "assignment__student", "event",
        )
        if teacher_assignments is not None:
            exams = exams.filter(_teacher_exam_q(teacher_assignments))
            results = results.filter(_teacher_result_q(teacher_assignments)).distinct()
        for param, field in (
            ("academic_session", "academic_session_id"), ("term", "term_id"),
            ("class_level", "class_level_id"), ("subject", "subject_id"), ("examination", "id"),
        ):
            value = self.request.query_params.get(param)
            if value:
                if param == "examination":
                    exams = exams.filter(pk=value)
                    results = results.filter(examination_id=value)
                else:
                    exams = exams.filter(**{field: value})
                    results = results.filter(**{f"examination__{field}": value})
        student_id = self.request.query_params.get("student")
        if student_id:
            if not student_id.isdigit():
                raise ValidationError({"student": "Student identifier must be numeric."})
            results = results.filter(assignment__student_id=int(student_id))
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        try:
            if start_date:
                date.fromisoformat(start_date)
                exams = exams.filter(starts_at__date__gte=start_date)
                results = results.filter(submitted_at__date__gte=start_date)
            if end_date:
                date.fromisoformat(end_date)
                exams = exams.filter(starts_at__date__lte=end_date)
                results = results.filter(submitted_at__date__lte=end_date)
        except ValueError as exc:
            raise ValidationError("Date filters must use YYYY-MM-DD format.") from exc
        return school, exams.distinct(), results.distinct()

    @staticmethod
    def result_row(result):
        student = result.assignment.student
        exam = result.examination
        return {
            "id": str(result.pk), "student_id": student.pk,
            "student_name": " ".join(part for part in (student.first_name, student.middle_name, student.last_name) if part),
            "admission_number": student.admission_number, "class_name": exam.class_level.name,
            "subject_name": exam.subject.name, "examination_id": str(exam.pk), "examination_title": exam.title,
            "academic_session_id": exam.academic_session_id, "academic_session_name": exam.academic_session.name,
            "term_id": exam.term_id, "term_name": exam.term.name if exam.term_id else "",
            "exam_date": exam.starts_at, "submitted_at": result.submitted_at,
            "synchronized_at": result.synchronized_at, "status": result.status,
            "total_questions": result.total_questions, "attempted_questions": result.attempted_questions,
            "unanswered_questions": result.unanswered_questions, "correct_answers": result.correct_answers,
            "incorrect_answers": result.incorrect_answers, "objective_score": result.objective_score,
            "score": result.score, "maximum_score": result.maximum_score,
            "percentage": result.percentage, "passed": result.passed,
        }


class CbtResultsDashboardView(CbtResultsBaseView):
    def get(self, request, **kwargs):
        school, exams, results = self.scoped_data()
        final = results.filter(status=CbtResult.Status.FINALIZED, percentage__isnull=False)
        attempted_assignments = results.values("assignment_id").distinct().count()
        assignments = ExaminationAssignment.objects.filter(examination__school=school, examination__in=exams, status=ExaminationAssignment.Status.ASSIGNED)
        teacher_assignments = _teacher_assignments(self, school)
        if teacher_assignments is not None:
            assignments = assignments.filter(_teacher_assignment_q(teacher_assignments))
        student_id = request.query_params.get("student")
        if student_id and student_id.isdigit():
            assignments = assignments.filter(student_id=int(student_id))
        total_assigned = assignments.values("student_id", "examination_id").distinct().count()
        metrics = final.aggregate(average=Avg("percentage"), highest=Max("percentage"), lowest=Min("percentage"))
        finalized_count = final.count()
        passed_count = final.filter(passed=True).count()
        failed_count = final.filter(passed=False).count()
        pending_manual = results.filter(status=CbtResult.Status.NEEDS_MARKING).count()
        pending_sync = LocalCbtSyncEvent.objects.filter(
            school=school, examination__in=exams,
        ).filter(Q(status=LocalCbtSyncEvent.Status.CONFLICT) | Q(status=LocalCbtSyncEvent.Status.ACCEPTED, result__isnull=True)).count()
        completed_exam_count = exams.filter(status=Examination.Status.COMPLETED).count()
        distribution = []
        bins = ((0, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101))
        for lower, upper in bins:
            upper_q = Q(percentage__lt=upper)
            if upper == 101:
                upper_q = Q(percentage__lte=100)
            count = final.filter(percentage__gte=lower).filter(upper_q).count()
            distribution.append({"label": f"{lower}–{min(upper, 100)}%", "count": count})
        class_performance = list(final.values("examination__class_level_id", "examination__class_level__name").annotate(
            students=Count("assignment__student", distinct=True), attempts=Count("id"), average=Avg("percentage"),
        ).order_by("examination__class_level__name"))
        subject_performance = list(final.values("examination__subject_id", "examination__subject__name").annotate(
            students=Count("assignment__student", distinct=True), attempts=Count("id"), average=Avg("percentage"),
        ).order_by("examination__subject__name"))
        comparison = list(final.values("examination_id", "examination__title").annotate(
            attempts=Count("id"), average=Avg("percentage"), passed=Count("id", filter=Q(passed=True)),
        ).order_by("examination__starts_at"))
        trend = list(final.annotate(month=TruncMonth("submitted_at")).values("month").annotate(
            attempts=Count("id"), average=Avg("percentage"),
        ).order_by("month"))
        question_stats = {}
        for details in results.values_list("mark_details", flat=True).iterator(chunk_size=500):
            for item in details:
                stats = question_stats.setdefault(item["question_id"], {
                    "question_id": item["question_id"], "prompt": item["prompt"], "attempts": 0,
                    "incorrect": 0, "unanswered": 0,
                })
                stats["attempts"] += int(item["attempted"])
                stats["unanswered"] += int(not item["attempted"])
                stats["incorrect"] += int(item.get("incorrect") is True)
        question_analysis = []
        for stats in question_stats.values():
            response_count = stats["attempts"] + stats["unanswered"]
            stats["failure_rate"] = round(100 * stats["incorrect"] / stats["attempts"], 2) if stats["attempts"] else None
            stats["unanswered_rate"] = round(100 * stats["unanswered"] / response_count, 2) if response_count else 0
            stats["small_sample"] = response_count < 5
            question_analysis.append(stats)
        question_analysis.sort(key=lambda item: (item["unanswered_rate"], item["failure_rate"] or 0), reverse=True)
        paginator = ResultPagination()
        page = paginator.paginate_queryset(results.order_by("-submitted_at"), request, view=self)
        rows = [self.result_row(item) for item in page]
        response = paginator.get_paginated_response(rows)
        response.data["summary"] = {
            "total_assigned": total_assigned, "participated": attempted_assignments,
            "not_participated": max(0, total_assigned - attempted_assignments),
            "completed_examinations": completed_exam_count,
            "average_score": round(metrics["average"], 2) if metrics["average"] is not None else None,
            "highest_score": metrics["highest"], "lowest_score": metrics["lowest"],
            "pass_rate": round(100 * passed_count / finalized_count, 2) if finalized_count else None,
            "failure_rate": round(100 * failed_count / finalized_count, 2) if finalized_count else None,
            "passed": passed_count, "failed": failed_count, "pending_manual_marking": pending_manual,
            "pending_sync": pending_sync, "sample_size": finalized_count, "small_sample": finalized_count < 5,
        }
        response.data["analytics"] = {
            "score_distribution": distribution,
            "class_performance": [{"id": row["examination__class_level_id"], "name": row["examination__class_level__name"], "students": row["students"], "attempts": row["attempts"], "average": round(row["average"], 2)} for row in class_performance],
            "subject_performance": [{"id": row["examination__subject_id"], "name": row["examination__subject__name"], "students": row["students"], "attempts": row["attempts"], "average": round(row["average"], 2)} for row in subject_performance],
            "examination_comparison": [{"id": str(row["examination_id"]), "name": row["examination__title"], "attempts": row["attempts"], "average": round(row["average"], 2), "pass_rate": round(100 * row["passed"] / row["attempts"], 2)} for row in comparison],
            "trend": [{"month": row["month"].date().isoformat(), "attempts": row["attempts"], "average": round(row["average"], 2)} for row in trend],
            "trend_sufficient": len(trend) >= 2,
            "question_analysis": question_analysis[:20],
        }
        response.data["filters"] = {
            "sessions": list(exams.values("academic_session_id", "academic_session__name").distinct().order_by("academic_session__name")),
            "terms": list(exams.exclude(term__isnull=True).values("term_id", "term__name").distinct().order_by("term__name")),
            "classes": list(exams.values("class_level_id", "class_level__name").distinct().order_by("class_level__name")),
            "subjects": list(exams.values("subject_id", "subject__name").distinct().order_by("subject__name")),
            "examinations": list(exams.values("id", "title").order_by("title")),
            "students": list(assignments.values("student_id", "student__admission_number", "student__first_name", "student__middle_name", "student__last_name").distinct().order_by("student__last_name", "student__first_name")[:500]),
        }
        return response


class CbtResultDetailView(CbtResultsBaseView):
    def get(self, request, result_id, **kwargs):
        school, _, results = self.scoped_data()
        result = results.filter(pk=result_id, school=school).first()
        if not result:
            from django.http import Http404
            raise Http404
        row = self.result_row(result)
        review_allowed = timezone.now() >= result.examination.ends_at
        details = []
        for item in result.mark_details:
            detail = dict(item)
            if not review_allowed:
                for field in ("correct_option_ids", "explanation", "correct", "incorrect"):
                    detail.pop(field, None)
            details.append(detail)
        row.update({
            "pass_mark": result.pass_mark,
            "review_allowed": review_allowed,
            "answer_release_at": result.examination.ends_at,
            "answers": details,
            "corrections": [{"reason": item.reason, "corrected_by": item.corrected_by.get_full_name() or item.corrected_by.email, "created_at": item.created_at} for item in result.corrections.select_related("corrected_by")],
        })
        return Response(row)


class CbtResultCorrectionView(CbtResultsBaseView):
    def post(self, request, result_id, **kwargs):
        school, _, results = self.scoped_data()
        result = results.filter(pk=result_id, school=school).first()
        if not result:
            from django.http import Http404
            raise Http404
        try:
            result = apply_result_correction(
                result, marks=request.data.get("marks"), reason=request.data.get("reason", ""), actor=request.user,
            )
        except DjangoValidationError as exc:
            details = getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])
            from rest_framework.exceptions import ValidationError as ApiValidationError
            raise ApiValidationError(details) from exc
        return Response({**self.result_row(result), "correction_count": result.corrections.count()})


class CbtResultsExportView(CbtResultsBaseView):
    def get(self, request, **kwargs):
        _, _, results = self.scoped_data()

        class Echo:
            def write(self, value):
                return value

        writer = csv.writer(Echo())
        header = writer.writerow(("Student", "Admission number", "Class", "Subject", "Examination", "Exam date", "Submitted", "Questions", "Attempted", "Unanswered", "Correct", "Incorrect", "Score", "Out of", "Percentage", "Result"))

        def output():
            yield header
            for result in results.order_by("-submitted_at").iterator(chunk_size=500):
                row = self.result_row(result)
                label = "Needs marking" if result.passed is None else "Passed" if result.passed else "Failed"
                yield writer.writerow((row["student_name"], row["admission_number"], row["class_name"], row["subject_name"], row["examination_title"], row["exam_date"].isoformat(), row["submitted_at"].isoformat(), row["total_questions"], row["attempted_questions"], row["unanswered_questions"], row["correct_answers"], row["incorrect_answers"], row["score"] or row["objective_score"], row["maximum_score"], row["percentage"] or "", label))

        response = StreamingHttpResponse(output(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="edustacked-cbt-results.csv"'
        return response
