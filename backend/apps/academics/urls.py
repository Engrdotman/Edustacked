from django.urls import path

from .views import (
    AcademicSessionDetailView, AcademicSessionListCreateView,
    ClassArmDetailView, ClassArmListCreateView,
    ClassLevelDetailView, ClassLevelListCreateView,
    ClassSubjectDetailView, ClassSubjectListCreateView,
    GradeBandDetailView, GradeBandListCreateView,
    GradingScaleDetailView, GradingScaleListCreateView,
    SubjectDetailView, SubjectListCreateView,
    TermDetailView, TermListCreateView,
)

urlpatterns = [
    path("academic-sessions/", AcademicSessionListCreateView.as_view(), name="academic-session-list"),
    path("academic-sessions/<int:pk>/", AcademicSessionDetailView.as_view(), name="academic-session-detail"),
    path("terms/", TermListCreateView.as_view(), name="term-list"),
    path("terms/<int:pk>/", TermDetailView.as_view(), name="term-detail"),
    path("classes/", ClassLevelListCreateView.as_view(), name="class-list"),
    path("classes/<int:pk>/", ClassLevelDetailView.as_view(), name="class-detail"),
    path("classes/<int:class_id>/arms/", ClassArmListCreateView.as_view(), name="class-arm-list"),
    path("classes/<int:class_id>/arms/<int:pk>/", ClassArmDetailView.as_view(), name="class-arm-detail"),
    path("classes/<int:class_id>/subjects/", ClassSubjectListCreateView.as_view(), name="class-subject-list"),
    path("classes/<int:class_id>/subjects/<int:pk>/", ClassSubjectDetailView.as_view(), name="class-subject-detail"),
    path("subjects/", SubjectListCreateView.as_view(), name="subject-list"),
    path("subjects/<int:pk>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("grading-scales/", GradingScaleListCreateView.as_view(), name="grading-scale-list"),
    path("grading-scales/<int:pk>/", GradingScaleDetailView.as_view(), name="grading-scale-detail"),
    path("grading-scales/<int:scale_id>/bands/", GradeBandListCreateView.as_view(), name="grade-band-list"),
    path("grading-scales/<int:scale_id>/bands/<int:pk>/", GradeBandDetailView.as_view(), name="grade-band-detail"),
]
