from django.urls import path

from .views import (
    AdmissionCreateView, EnrollmentDetailView, EnrollmentTransferView,
    EnrollmentTransitionView, GuardianDetailView, GuardianListCreateView,
    StudentDetailView, StudentEnrollmentListCreateView, StudentGuardianDetailView,
    StudentGuardianListCreateView, StudentListCreateView, StudentPhotoView,
)

urlpatterns = [
    path("admissions/", AdmissionCreateView.as_view(), name="student-admission"),
    path("students/", StudentListCreateView.as_view(), name="student-list"),
    path("students/<int:pk>/", StudentDetailView.as_view(), name="student-detail"),
    path("students/<int:pk>/photo/", StudentPhotoView.as_view(), name="student-photo"),
    path("students/<int:student_id>/guardians/", StudentGuardianListCreateView.as_view(), name="student-guardian-list"),
    path("students/<int:student_id>/guardians/<int:pk>/", StudentGuardianDetailView.as_view(), name="student-guardian-detail"),
    path("students/<int:student_id>/enrollments/", StudentEnrollmentListCreateView.as_view(), name="student-enrollment-list"),
    path("guardians/", GuardianListCreateView.as_view(), name="guardian-list"),
    path("guardians/<int:pk>/", GuardianDetailView.as_view(), name="guardian-detail"),
    path("enrollments/<int:pk>/", EnrollmentDetailView.as_view(), name="enrollment-detail"),
    path("enrollments/<int:pk>/transition/", EnrollmentTransitionView.as_view(), name="enrollment-transition"),
    path("enrollments/<int:pk>/transfer/", EnrollmentTransferView.as_view(), name="enrollment-transfer"),
]
