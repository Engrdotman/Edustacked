from django.urls import path

from .views import PlatformEntitlementListCreateView, SchoolEntitlementLicenseView, SchoolEntitlementListView, SchoolServicePlanListView

urlpatterns = [
    path("services/plans/", SchoolServicePlanListView.as_view(), name="service-plans"),
    path("services/entitlements/", SchoolEntitlementListView.as_view(), name="school-service-entitlements"),
    path("services/entitlements/<uuid:entitlement_id>/license/", SchoolEntitlementLicenseView.as_view(), name="school-service-entitlement-license"),
    path("platform/services/entitlements/", PlatformEntitlementListCreateView.as_view(), name="platform-service-entitlements"),
]
