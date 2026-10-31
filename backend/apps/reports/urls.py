from django.urls import path

from .views import (
    AcademicReportView,
    AttendanceReportView,
    EnrollmentReportView,
    FinanceReportView,
    ReportCardReportView,
    ReportsDashboardView,
)

urlpatterns = [
    path("dashboard/", ReportsDashboardView.as_view(), name="reports-dashboard"),
    path("enrollment/", EnrollmentReportView.as_view(), name="reports-enrollment"),
    path("attendance/", AttendanceReportView.as_view(), name="reports-attendance"),
    path("academics/", AcademicReportView.as_view(), name="reports-academics"),
    path("report-cards/", ReportCardReportView.as_view(), name="reports-report-cards"),
    path("finance/", FinanceReportView.as_view(), name="reports-finance"),
]
