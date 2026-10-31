from django.urls import path

from .views import (
    SchoolCreateView,
    SchoolMembershipDetailView,
    SchoolMembershipListCreateView,
    SchoolLogoView,
    SchoolProfileView,
    SchoolSettingsView,
    SchoolOwnershipTransferView,
)
from .onboarding import SchoolOnboardingView
from .platform_views import PlatformSchoolsView, PlatformSchoolDetailView, PlatformSchoolActionView

urlpatterns = [
    path("platform/schools/", PlatformSchoolsView.as_view(), name="platform-schools"),
    path("platform/schools/<int:pk>/", PlatformSchoolDetailView.as_view(), name="platform-school-detail"),
    path("platform/schools/<int:pk>/<str:action>/", PlatformSchoolActionView.as_view(), name="platform-school-action"),
    path("", SchoolCreateView.as_view(), name="school-create"),
    path("profile/", SchoolProfileView.as_view(), name="school-profile"),
    path("settings/", SchoolSettingsView.as_view(), name="school-settings"),
    path("onboarding/", SchoolOnboardingView.as_view(), name="school-onboarding"),
    path("<str:school_id>/ownership/transfer/", SchoolOwnershipTransferView.as_view(), name="school-ownership-transfer"),
    path("profile/logo/", SchoolLogoView.as_view(), name="school-logo"),
    path(
        "<str:school_id>/memberships/",
        SchoolMembershipListCreateView.as_view(),
        name="school-memberships",
    ),
    path(
        "<str:school_id>/memberships/<int:pk>/",
        SchoolMembershipDetailView.as_view(),
        name="school-membership-detail",
    ),
]
