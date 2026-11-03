from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.schools.permissions import HasSchoolPermission, IsPlatformSuperadmin
from apps.schools.tenancy import resolve_authorized_school

from .models import ServiceEntitlement, ServicePlan
from .serializers import ServiceEntitlementSerializer, ServicePlanSerializer


class SchoolServicePlanListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "services.view"
    serializer_class = ServicePlanSerializer

    def get_queryset(self):
        resolve_authorized_school(self.request.user, self.request.headers.get("X-School-ID"))
        return ServicePlan.objects.filter(is_active=True)


class SchoolEntitlementListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "services.view"
    serializer_class = ServiceEntitlementSerializer

    def get_queryset(self):
        school = resolve_authorized_school(self.request.user, self.request.headers.get("X-School-ID"))
        return ServiceEntitlement.objects.filter(school=school).select_related("school", "plan")


class PlatformEntitlementListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)
    serializer_class = ServiceEntitlementSerializer
    queryset = ServiceEntitlement.objects.select_related("school", "plan")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
