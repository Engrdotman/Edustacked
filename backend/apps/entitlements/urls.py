from django.urls import path

from .views import PlatformEntitlementListCreateView, SchoolEntitlementListView, SchoolServicePlanListView

urlpatterns = [
    path("services/plans/", SchoolServicePlanListView.as_view(), name="service-plans"),
    path("services/entitlements/", SchoolEntitlementListView.as_view(), name="school-service-entitlements"),
    path("platform/services/entitlements/", PlatformEntitlementListCreateView.as_view(), name="platform-service-entitlements"),
]
