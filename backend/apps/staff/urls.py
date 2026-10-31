from django.urls import path

from .views import (
    AssignmentDetailView, AssignmentListCreateView, AssignmentReplacementView,
    AssignmentTransitionView, StaffDetailView, StaffListCreateView,
    StaffMeView, TeacherDesignationView,
)

urlpatterns = [
    path("staff/", StaffListCreateView.as_view(), name="staff-list"),
    path("staff/me/", StaffMeView.as_view(), name="staff-me"),
    path("staff/<int:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("staff/<int:pk>/teacher/", TeacherDesignationView.as_view(), name="staff-teacher-designation"),
    path("assignments/", AssignmentListCreateView.as_view(), name="teacher-assignment-list"),
    path("assignments/<int:pk>/", AssignmentDetailView.as_view(), name="teacher-assignment-detail"),
    path("assignments/<int:pk>/transition/", AssignmentTransitionView.as_view(), name="teacher-assignment-transition"),
    path("assignments/<int:pk>/replace/", AssignmentReplacementView.as_view(), name="teacher-assignment-replace"),
]
