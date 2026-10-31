from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.permissions import authorized_membership
from apps.schools.tenancy import SchoolScopedQuerySetMixin
from .models import StaffProfile, TeacherAssignment, TeacherProfile
from .permissions import HasStaffPermission
from .serializers import (
    AssignmentSerializer, AssignmentTransitionSerializer, StaffDirectorySerializer,
    StaffProfileSerializer, TeacherProfileSerializer,
)


class StaffPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class StaffViewMixin(SchoolScopedQuerySetMixin):
    permission_classes = (IsAuthenticated, HasStaffPermission)
    pagination_class = StaffPagination

    def get_school(self):
        return self.get_authorized_school()

    def get_serializer_context(self):
        context = {"request": self.request, "view": self, "format": self.format_kwarg, "school": self.get_school()}
        return context

    def role(self):
        if self.request.user.is_superuser:
            return "school_admin"
        return authorized_membership(self.request.user, self.request, self).role


class StaffListCreateView(StaffViewMixin, ListCreateAPIView):
    queryset = StaffProfile.objects.select_related("school", "user").prefetch_related("teacher_profile")
    staff_permissions = {"GET": "staff.view", "POST": "staff.manage"}

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if len(search) > 100:
            raise serializers.ValidationError({"search": "Search must be 100 characters or fewer."})
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(staff_number__icontains=search) | Q(first_name__icontains=search) | Q(middle_name__icontains=search) | Q(last_name__icontains=search) | Q(job_title__icontains=search))
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in StaffProfile.Status.values:
                raise serializers.ValidationError({"status": "Use active, inactive, suspended, or former."})
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST" or self.role() in ("school_admin", "school_manager"):
            return StaffProfileSerializer
        return StaffDirectorySerializer

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class StaffDetailView(StaffViewMixin, RetrieveUpdateAPIView):
    queryset = StaffProfile.objects.select_related("school", "user")
    staff_permissions = {"GET": "staff.view", "PATCH": "staff.manage", "PUT": "staff.manage"}
    http_method_names = ("get", "patch", "head", "options")

    def get_serializer_class(self):
        return StaffProfileSerializer if self.role() in ("school_admin", "school_manager") else StaffDirectorySerializer


class StaffMeView(StaffViewMixin, APIView):
    staff_permissions = {"GET": "teacher.profile.view"}

    def get(self, request, **kwargs):
        profile = get_object_or_404(StaffProfile.objects.filter(school=self.get_school(), user=request.user))
        teacher = getattr(profile, "teacher_profile", None)
        return Response({
            "staff": StaffDirectorySerializer(profile).data,
            "teacher": TeacherProfileSerializer(teacher, context=self.get_serializer_context()).data if teacher else None,
        })


class TeacherDesignationView(StaffViewMixin, APIView):
    staff_permissions = {"GET": "staff.manage", "POST": "staff.manage", "PATCH": "staff.manage"}

    def get_profile(self, pk):
        return get_object_or_404(StaffProfile.objects.filter(school=self.get_school()), pk=pk)

    def get(self, request, pk, **kwargs):
        profile = self.get_profile(pk)
        teacher = get_object_or_404(TeacherProfile.objects.filter(school=self.get_school()), staff=profile)
        return Response(TeacherProfileSerializer(teacher, context=self.get_serializer_context()).data)

    def post(self, request, pk, **kwargs):
        profile = self.get_profile(pk)
        serializer = TeacherProfileSerializer(data={**request.data, "staff": profile.pk}, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        return Response(TeacherProfileSerializer(teacher, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk, **kwargs):
        profile = self.get_profile(pk)
        teacher = get_object_or_404(TeacherProfile.objects.filter(school=self.get_school()), staff=profile)
        serializer = TeacherProfileSerializer(teacher, data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return Response(TeacherProfileSerializer(serializer.save(), context=self.get_serializer_context()).data)


class AssignmentListCreateView(StaffViewMixin, ListCreateAPIView):
    queryset = TeacherAssignment.objects.select_related("teacher__staff", "academic_session", "class_level", "class_arm", "subject")
    staff_permissions = {"GET": "teacher_assignments.view", "POST": "teacher_assignments.manage"}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.role() == "teacher":
            qs = qs.filter(teacher__staff__user=self.request.user)
        for param, field, model in (
            ("academic_session", "academic_session_id", "academic_sessions"),
            ("class_level", "class_level_id", "class_levels"),
            ("class_arm", "class_arm_id", "class_arms"),
            ("subject", "subject_id", "subjects"),
        ):
            value = self.request.query_params.get(param)
            if value:
                if not value.isdecimal():
                    raise serializers.ValidationError({param: "Use a valid ID."})
                qs = qs.filter(**{field: int(value)})
        teacher_id = self.request.query_params.get("teacher")
        if teacher_id:
            if not teacher_id.isdecimal():
                raise serializers.ValidationError({"teacher": "Use a valid teacher profile ID."})
            qs = qs.filter(teacher_id=int(teacher_id))
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in TeacherAssignment.Status.values:
                raise serializers.ValidationError({"status": "Use active, ended, or cancelled."})
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        return AssignmentSerializer

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class AssignmentDetailView(StaffViewMixin, RetrieveAPIView):
    queryset = TeacherAssignment.objects.select_related("teacher__staff", "academic_session", "class_level", "class_arm", "subject")
    serializer_class = AssignmentSerializer
    staff_permissions = {"GET": "teacher_assignments.view"}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.role() == "teacher":
            qs = qs.filter(teacher__staff__user=self.request.user)
        return qs


class AssignmentTransitionView(StaffViewMixin, APIView):
    staff_permissions = {"POST": "teacher_assignments.manage"}

    def post(self, request, pk, **kwargs):
        assignment = get_object_or_404(TeacherAssignment.objects.filter(school=self.get_school()), pk=pk)
        serializer = AssignmentTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                assignment = TeacherAssignment.objects.select_for_update().get(pk=assignment.pk)
                if assignment.status != TeacherAssignment.Status.ACTIVE:
                    raise serializers.ValidationError({"status": "Only active assignments can be ended or cancelled."})
                assignment.status = serializer.validated_data["status"]
                assignment.end_date = serializer.validated_data["end_date"]
                assignment.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Invalid assignment transition.") from exc
        return Response(AssignmentSerializer(assignment, context=self.get_serializer_context()).data)


class AssignmentReplacementView(StaffViewMixin, APIView):
    staff_permissions = {"POST": "teacher_assignments.manage"}

    def post(self, request, pk, **kwargs):
        old = get_object_or_404(TeacherAssignment.objects.filter(school=self.get_school()), pk=pk)
        payload = request.data.copy()
        payload["reason"] = payload.get("reason", "")
        serializer = AssignmentSerializer(data=payload, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        replacement_reason = data.pop("reason", "")
        try:
            with transaction.atomic():
                old = TeacherAssignment.objects.select_for_update().get(pk=old.pk)
                if old.status != TeacherAssignment.Status.ACTIVE:
                    raise serializers.ValidationError({"status": "Only an active assignment can be replaced."})
                if data["start_date"] <= old.start_date:
                    raise serializers.ValidationError({"start_date": "Replacement must start after the existing assignment began."})
                old.status = TeacherAssignment.Status.ENDED
                old.end_date = data["start_date"] - timedelta(days=1)
                old.save()
                replacement = TeacherAssignment.objects.create(
                    **data, school=self.get_school(), previous_assignment=old,
                    change_reason=replacement_reason,
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Assignment replacement could not be completed.") from exc
        return Response(AssignmentSerializer(replacement, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)
