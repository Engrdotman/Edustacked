from django.urls import path

from .views import (
    SchoolCreateView,
    SchoolMembershipDetailView,
    SchoolMembershipListCreateView,
)

urlpatterns = [
    path("", SchoolCreateView.as_view(), name="school-create"),
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
