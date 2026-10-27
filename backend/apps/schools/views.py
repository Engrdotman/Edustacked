from rest_framework.generics import CreateAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated

from .models import School, SchoolMembership
from .permissions import HasSchoolPermission, IsPlatformSuperadmin
from .serializers import (
    MembershipAdminUpdateSerializer,
    MembershipProvisionSerializer,
    SchoolCreateSerializer,
)
from .tenancy import SchoolScopedQuerySetMixin
from apps.accounts.serializers import SchoolMembershipSerializer


class SchoolCreateView(CreateAPIView):
    queryset = School.objects.all()
    serializer_class = SchoolCreateSerializer
    permission_classes = (IsPlatformSuperadmin,)


class SchoolMembershipListCreateView(SchoolScopedQuerySetMixin, ListCreateAPIView):
    queryset = SchoolMembership.objects.select_related("school", "user")
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "memberships.manage"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MembershipProvisionSerializer
        return SchoolMembershipSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["school"] = self.get_authorized_school()
        return context


class SchoolMembershipDetailView(SchoolScopedQuerySetMixin, RetrieveUpdateAPIView):
    queryset = SchoolMembership.objects.select_related("school", "user")
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "memberships.manage"
    http_method_names = ("get", "patch", "head", "options")

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return MembershipAdminUpdateSerializer
        return SchoolMembershipSerializer
