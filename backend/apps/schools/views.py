from django.db import transaction
from django.http import FileResponse
from django.db import transaction
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import School, SchoolMembership
from .permissions import HasSchoolPermission, HasSchoolProfileAccess, IsPlatformSuperadmin
from .serializers import (
    MembershipAdminUpdateSerializer,
    MembershipProvisionSerializer,
    SchoolCreateSerializer,
    SchoolLogoSerializer,
    SchoolProfileSerializer,
    SchoolSettingsSerializer,
)
from .models import SchoolSettings
from .models import SchoolVerificationEvent
from .tenancy import SchoolScopedQuerySetMixin
from apps.accounts.serializers import SchoolMembershipSerializer
from .onboarding import SchoolOnboardingView, OwnershipTransferSerializer


class SchoolCreateView(CreateAPIView):
    queryset = School.objects.all()
    serializer_class = SchoolCreateSerializer
    permission_classes = (IsPlatformSuperadmin,)


class SchoolProfileView(RetrieveUpdateAPIView):
    serializer_class = SchoolProfileSerializer
    permission_classes = (IsAuthenticated, HasSchoolProfileAccess)
    http_method_names = ("get", "patch", "head", "options")

    def get_object(self):
        from .tenancy import resolve_authorized_school

        identifier = self.request.headers.get("X-School-ID")
        return resolve_authorized_school(self.request.user, identifier)


class SchoolSettingsView(RetrieveUpdateAPIView):
    serializer_class = SchoolSettingsSerializer
    permission_classes = (IsAuthenticated, HasSchoolProfileAccess)
    http_method_names = ("get", "patch", "head", "options")

    def get_object(self):
        from .tenancy import resolve_authorized_school

        school = resolve_authorized_school(
            self.request.user, self.request.headers.get("X-School-ID")
        )
        settings, _ = SchoolSettings.objects.get_or_create(school=school)
        return settings


class SchoolLogoView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolProfileAccess)
    parser_classes = (MultiPartParser, FormParser)

    def _school(self, request):
        from .tenancy import resolve_authorized_school

        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))

    def get(self, request, version=None):
        school = self._school(request)
        if not school.logo:
            return Response({"detail": "This school has no logo."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(school.logo.open("rb"), content_type="image/" + school.logo.name.rsplit(".", 1)[-1].lower().replace("jpg", "jpeg"))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, version=None):
        school = self._school(request)
        serializer = SchoolLogoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_logo = school.logo
        school.logo = serializer.validated_data["logo"]
        school.save(update_fields=("logo", "updated_at"))
        if previous_logo:
            transaction.on_commit(lambda: previous_logo.delete(save=False))
        return Response(SchoolProfileSerializer(school).data)


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


class SchoolOwnershipTransferView(SchoolScopedQuerySetMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "memberships.manage"

    def post(self, request, school_id, **kwargs):
        school = self.get_authorized_school()
        current_membership = SchoolMembership.objects.get(user=request.user, school=school, is_active=True)
        if current_membership.role != SchoolMembership.Role.SCHOOL_OWNER:
            return Response({"detail": "Only the current school owner can transfer ownership."}, status=403)
        serializer = OwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["password"]):
            return Response({"password": ["The password is incorrect."]}, status=400)
        try:
            target = SchoolMembership.objects.select_related("user").get(
                pk=serializer.validated_data["target_membership_id"], school=school,
                is_active=True, user__is_active=True,
            )
        except SchoolMembership.DoesNotExist:
            return Response({"detail": "Choose an active member of this school."}, status=400)
        if target.pk == current_membership.pk or target.user.email_verified_at is None:
            return Response({"detail": "Ownership can only be transferred to another member with a verified email."}, status=400)
        with transaction.atomic():
            locked_school = School.objects.select_for_update().get(pk=school.pk)
            current_membership = SchoolMembership.objects.select_for_update().get(pk=current_membership.pk)
            target = SchoolMembership.objects.select_for_update().get(pk=target.pk)
            if current_membership.role != SchoolMembership.Role.SCHOOL_OWNER:
                return Response({"detail": "Ownership has already changed. Refresh and try again."}, status=409)
            current_membership.role = SchoolMembership.Role.SCHOOL_ADMIN
            target.role = SchoolMembership.Role.SCHOOL_OWNER
            current_membership.save(update_fields=("role",))
            target.save(update_fields=("role",))
            SchoolVerificationEvent.objects.create(
                school=locked_school, actor=request.user, action="ownership_transferred",
                from_status=locked_school.verification_status, to_status=locked_school.verification_status,
                reason=serializer.validated_data["reason"].strip(),
                metadata={"previous_owner_id": request.user.pk, "new_owner_id": target.user_id},
            )
        return Response({"detail": "School ownership has been transferred."})
