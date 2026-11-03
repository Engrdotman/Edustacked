from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import Http404

from apps.schools.models import SchoolMembership
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


class SchoolEntitlementLicenseView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "services.manage"

    def get(self, request, entitlement_id, version=None):
        school = resolve_authorized_school(request.user, request.headers.get("X-School-ID"))
        if not request.user.is_superuser and not SchoolMembership.objects.filter(
            user=request.user, school=school, is_active=True,
            role__in=(SchoolMembership.Role.SCHOOL_OWNER, SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.PRINCIPAL),
        ).exists():
            raise PermissionDenied("Only a school owner, administrator, or principal can download its signed license.")
        entitlement = ServiceEntitlement.objects.filter(
            pk=entitlement_id, school=school, service_code="offline_cbt",
            status=ServiceEntitlement.Status.ACTIVE,
        ).first()
        if not entitlement:
            raise Http404
        return Response({
            "license_id": str(entitlement.license_id), "signed_license": entitlement.signed_license,
            "expires_on": entitlement.expires_on,
        })


class PlatformEntitlementListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)
    serializer_class = ServiceEntitlementSerializer
    queryset = ServiceEntitlement.objects.select_related("school", "plan")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
