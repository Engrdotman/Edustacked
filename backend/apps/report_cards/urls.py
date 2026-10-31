from django.urls import path

from .views import (
    ReportCardActionView, ReportCardDetailView, ReportCardGenerateClassView,
    ReportCardGenerateView, ReportCardListView, ReportCardPdfView,
)

urlpatterns = [
    path("report-cards/", ReportCardListView.as_view(), name="report-card-list"),
    path("report-cards/generate/", ReportCardGenerateView.as_view(), name="report-card-generate"),
    path("report-cards/generate-class/", ReportCardGenerateClassView.as_view(), name="report-card-generate-class"),
    path("report-cards/<int:pk>/", ReportCardDetailView.as_view(), name="report-card-detail"),
    path("report-cards/<int:pk>/pdf/", ReportCardPdfView.as_view(), name="report-card-pdf"),
    path("report-cards/<int:pk>/<str:action>/", ReportCardActionView.as_view(), name="report-card-action"),
]
