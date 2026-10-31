from django.urls import path

from .views import (
    AttendanceBulkUpdateView, AttendanceRecordListView, AttendanceRecordUpdateView,
    AttendanceRegisterActionView, AttendanceRegisterCreateView,
    AttendanceRegisterDetailView, AttendanceRegisterListView,
    AttendanceReportView, EligibleStudentsView, StudentAttendanceHistoryView,
    AttendanceOptionsView,
)

urlpatterns = [
    path("attendance/options/", AttendanceOptionsView.as_view(), name="attendance-options"),
    path("attendance/eligible-students/", EligibleStudentsView.as_view(), name="attendance-eligible-students"),
    path("attendance/registers/", AttendanceRegisterListView.as_view(), name="attendance-register-list"),
    path("attendance/registers/create/", AttendanceRegisterCreateView.as_view(), name="attendance-register-create"),
    path("attendance/registers/<int:pk>/", AttendanceRegisterDetailView.as_view(), name="attendance-register-detail"),
    path("attendance/registers/<int:pk>/records/", AttendanceBulkUpdateView.as_view(), name="attendance-register-records"),
    path("attendance/registers/<int:pk>/<str:action>/", AttendanceRegisterActionView.as_view(), name="attendance-register-action"),
    path("attendance/records/", AttendanceRecordListView.as_view(), name="attendance-record-list"),
    path("attendance/records/<int:pk>/", AttendanceRecordUpdateView.as_view(), name="attendance-record-detail"),
    path("attendance/students/<int:student_id>/history/", StudentAttendanceHistoryView.as_view(), name="attendance-student-history"),
    path("attendance/reports/summary/", AttendanceReportView.as_view(), name="attendance-report-summary"),
]
