from django.urls import path

from .views import (
    GuardianActivationView, GuardianAnnouncementListView,
    GuardianAttendanceView, GuardianNotificationListView,
    GuardianNotificationReadView, GuardianProfileView,
    GuardianReportCardDetailView, GuardianReportCardListView,
    GuardianReportCardPdfView, GuardianInvitationCreateView,
    LinkedStudentDetailView, LinkedStudentListView, StaffAnnouncementView,
)

urlpatterns = [
    path("guardian/activate/", GuardianActivationView.as_view(), name="guardian-activate"),
    path("parent/profile/", GuardianProfileView.as_view(), name="parent-profile"),
    path("parent/students/", LinkedStudentListView.as_view(), name="parent-students"),
    path("parent/students/<int:student_id>/", LinkedStudentDetailView.as_view(), name="parent-student-detail"),
    path("parent/students/<int:student_id>/attendance/", GuardianAttendanceView.as_view(), name="parent-attendance"),
    path("parent/students/<int:student_id>/report-cards/", GuardianReportCardListView.as_view(), name="parent-report-cards"),
    path("parent/report-cards/<int:revision_id>/pdf/", GuardianReportCardPdfView.as_view(), name="parent-report-card-pdf"),
    path("parent/report-cards/<int:revision_id>/", GuardianReportCardDetailView.as_view(), name="parent-report-card-detail"),
    path("parent/announcements/", GuardianAnnouncementListView.as_view(), name="parent-announcements"),
    path("parent/notifications/", GuardianNotificationListView.as_view(), name="parent-notifications"),
    path("parent/notifications/<int:pk>/read/", GuardianNotificationReadView.as_view(), name="parent-notification-read"),
    path("parent/staff/students/<int:student_id>/guardians/<int:link_id>/invite/", GuardianInvitationCreateView.as_view(), name="guardian-invitation-create"),
    path("parent/staff/announcements/", StaffAnnouncementView.as_view(), name="parent-announcement-list-create"),
    path("parent/staff/announcements/<int:pk>/", StaffAnnouncementView.as_view(), name="parent-announcement-update"),
    path("parent/staff/announcements/<int:pk>/publish/", StaffAnnouncementView.as_view(), {"action": "publish"}, name="parent-announcement-publish"),
    path("parent/staff/announcements/<int:pk>/archive/", StaffAnnouncementView.as_view(), {"action": "archive"}, name="parent-announcement-archive"),
]
