import csv

from django.http import StreamingHttpResponse
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import CreditPayment
from apps.schools.models import SchoolMembership
from apps.schools.permissions import HasSchoolPermission, ROLE_PERMISSIONS, authorized_membership
from apps.schools.tenancy import resolve_authorized_school
from .services import (
    academic_report, attendance_report, attendance_summary, attendance_queryset,
    dashboard_metrics, enrollment_report, finance_report, parse_report_filters,
    report_card_report, teacher_assignments,
)


class ReportPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class CsvEcho:
    def write(self, value):
        return value


def safe_csv_value(value):
    if value is None:
        return ""
    text = str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_response(headers, rows, filename):
    writer = csv.writer(CsvEcho())

    def stream():
        yield writer.writerow([safe_csv_value(value) for value in headers])
        for row in rows:
            yield writer.writerow([safe_csv_value(value) for value in row])

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ReportAPIView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "reports.dashboard"

    def school(self, request):
        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))

    def role(self, request):
        if request.user.is_superuser:
            return SchoolMembership.Role.SCHOOL_ADMIN
        return authorized_membership(request.user, request, self).role

    def permissions_for(self, request):
        if request.user.is_superuser:
            return ROLE_PERMISSIONS[SchoolMembership.Role.SCHOOL_ADMIN]
        return ROLE_PERMISSIONS.get(self.role(request), frozenset())

    def filters(self, request, school):
        return parse_report_filters(request, school)

    def assignments(self, request, school, filters):
        if self.role(request) != SchoolMembership.Role.TEACHER:
            return None
        return teacher_assignments(school, request.user, filters)

    def filename(self, prefix, filters):
        dates = f"{filters['start_date']}-{filters['end_date']}"
        return f"{prefix}-{dates}.csv"


class ReportsDashboardView(ReportAPIView):
    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        return Response(dashboard_metrics(school, request.user, self.role(request), filters, self.permissions_for(request)))


class EnrollmentReportView(ReportAPIView):
    required_school_permission = "reports.enrollment"

    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        include_students = filters.get("view") == "students"
        report = enrollment_report(school, filters, include_students=include_students)
        if include_students:
            rows = report.pop("students")
            search = filters.get("search", "").strip()
            if search:
                from django.db.models import Q
                rows = rows.filter(Q(student__first_name__icontains=search) | Q(student__middle_name__icontains=search) | Q(student__last_name__icontains=search) | Q(student__admission_number__icontains=search))
            if filters.get("export") == "csv":
                def exported():
                    for row in rows.iterator(chunk_size=1000):
                        yield (row.student.admission_number, row.student.first_name, row.student.middle_name,
                               row.student.last_name, row.academic_session.name, row.class_level.name,
                               row.class_arm.name, row.status, row.enrollment_date,
                               row.withdrawal_date, row.transfer_date)
                return csv_response(("Admission number", "First name", "Middle name", "Last name", "Session", "Class", "Arm", "Enrollment status", "Enrollment date", "Withdrawal date", "Transfer date"), exported(), self.filename("enrollment-students", filters))
            paginator = ReportPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            report["students"] = paginator.get_paginated_response([{
                "id": row.student_id, "admission_number": row.student.admission_number,
                "name": " ".join(filter(None, (row.student.first_name, row.student.middle_name, row.student.last_name))),
                "session": row.academic_session.name, "class_name": row.class_level.name,
                "arm_name": row.class_arm.name, "status": row.status,
                "enrollment_date": row.enrollment_date,
            } for row in page]).data
        elif filters.get("export") == "csv":
            distribution = report["distribution"]
            return csv_response(("Class", "Arm", "Enrollment status", "Students"), ((row["class_level__name"], row["class_arm__name"], row["status"], row["count"]) for row in distribution), self.filename("enrollment-distribution", filters))
        return Response(report)


class AttendanceReportView(ReportAPIView):
    required_school_permission = "reports.attendance"

    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        assignments = self.assignments(request, school, filters)
        rows = attendance_report(school, filters, assignments, by_student=filters.get("view") == "students")
        if filters.get("export") == "csv":
            if filters.get("view") == "students":
                values = ((row["student__admission_number"], " ".join(filter(None, (row["student__first_name"], row["student__middle_name"], row["student__last_name"]))), row["register__academic_session__name"], row["register__class_level__name"], row["register__class_arm__name"], row["total"], row["present"], row["absent"], row["late"], row["excused"], round((row["present"] + row["late"]) * 100 / row["total"], 2) if row["total"] else "") for row in rows)
                return csv_response(("Admission number", "Student", "Session", "Class", "Arm", "Marked records", "Present", "Absent", "Late", "Excused", "Attendance percent"), values, self.filename("attendance-students", filters))
            values = ((row["register__attendance_date"], row["register__class_level__name"], row["register__class_arm__name"], row["total"], row["present"], row["absent"], row["late"], row["excused"], round((row["present"] + row["late"]) * 100 / row["total"], 2) if row["total"] else "") for row in rows)
            return csv_response(("Date", "Class", "Arm", "Marked records", "Present", "Absent", "Late", "Excused", "Attendance percent"), values, self.filename("attendance", filters))
        if filters.get("view") == "students":
            paginator = ReportPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            response = paginator.get_paginated_response(page)
            response.data["date_range"] = {"start": filters["start_date"], "end": filters["end_date"]}
            response.data["policy"] = attendance_summary(attendance_queryset(school, filters, assignments))["policy"]
            return response
        return Response({"date_range": {"start": filters["start_date"], "end": filters["end_date"]}, "summary": attendance_summary(attendance_queryset(school, filters, assignments)), "rows": rows})


class AcademicReportView(ReportAPIView):
    required_school_permission = "reports.academics"

    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        reports = academic_report(school, filters, self.assignments(request, school, filters))
        if filters.get("export") == "csv":
            values = ((row["session"], row["term"], row["class_name"], row["arm_name"], row["subject"], row["plan_status"], row["approved"], row["submitted"], row["draft"], row["average_approved_percentage"], "; ".join(f"{grade['approved_grade'] or 'Unspecified'}: {grade['count']}" for grade in row["grade_distribution"])) for row in reports)
            return csv_response(("Session", "Term", "Class", "Arm", "Subject", "Plan status", "Approved results", "Submitted results", "Draft results", "Average approved percent", "Approved grade distribution"), values, self.filename("academic-performance", filters))
        return Response({"source": "approved results are used for averages and grade distribution; submitted and draft counts are workflow progress only", "plans": reports})


class ReportCardReportView(ReportAPIView):
    required_school_permission = "reports.report_cards"

    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        report = report_card_report(school, filters, self.assignments(request, school, filters))
        if filters.get("export") == "csv":
            values = ((row["class_name"], row["arm_name"], row["expected_students"], row["draft"], row["review"], row["approved"], row["published"], row["publication_percentage"]) for row in report["classes"])
            return csv_response(("Class", "Arm", "Expected students", "Draft", "Review", "Approved", "Published", "Publication percent"), values, self.filename("report-card-status", filters))
        return Response(report)


class FinanceReportView(ReportAPIView):
    required_school_permission = "reports.finance"

    def get(self, request, **kwargs):
        school = self.school(request)
        filters = self.filters(request, school)
        if filters.get("export") == "csv":
            payments = CreditPayment.objects.filter(school=school, created_at__date__gte=filters["start_date"], created_at__date__lte=filters["end_date"]).order_by("created_at", "id")
            def exported():
                for payment in payments.iterator(chunk_size=1000):
                    yield (payment.reference, payment.status, payment.package_name, payment.credits,
                           payment.currency, payment.amount_minor, payment.created_at, payment.verified_at)
            return csv_response(("Payment reference", "Status", "Package", "Credits", "Currency", "Amount in minor units", "Created at", "Verified at"), exported(), self.filename("credit-payments", filters))
        return Response(finance_report(school, filters))
