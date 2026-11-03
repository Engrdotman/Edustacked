from django.urls import path

from .views import (
    LocalAdminOverviewView,
    LocalDatabaseBackupView,
    PackageImportView,
    StudentAnswerView,
    StudentExamListView,
    StudentExamStartView,
    StudentLoginView,
    StudentLogoutView,
    StudentSessionView,
    StudentSubmitView,
    SyncDashboardView,
)

urlpatterns = [
    path("auth/login/", StudentLoginView.as_view(), name="local-student-login"),
    path("auth/logout/", StudentLogoutView.as_view(), name="local-student-logout"),
    path("exams/", StudentExamListView.as_view(), name="local-student-exams"),
    path("exams/<uuid:package_id>/start/", StudentExamStartView.as_view(), name="local-student-exam-start"),
    path("sessions/<uuid:session_id>/", StudentSessionView.as_view(), name="local-student-session"),
    path("sessions/<uuid:session_id>/answers/", StudentAnswerView.as_view(), name="local-student-answer"),
    path("sessions/<uuid:session_id>/submit/", StudentSubmitView.as_view(), name="local-student-submit"),
    path("admin/overview/", LocalAdminOverviewView.as_view(), name="local-admin-overview"),
    path("admin/packages/import/", PackageImportView.as_view(), name="local-admin-package-import"),
    path("admin/sync/", SyncDashboardView.as_view(), name="local-admin-sync"),
    path("admin/backup/", LocalDatabaseBackupView.as_view(), name="local-admin-backup"),
]
