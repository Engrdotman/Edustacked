from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassLevel
from apps.staff.models import StaffProfile
from apps.students.models import Student
from .models import School, SchoolMembership, SchoolOnboardingProgress, SchoolVerificationEvent
from .permissions import IsPlatformSuperadmin
from .serializers import SchoolProfileSerializer


class PlatformSchoolPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class PlatformSchoolSerializer(serializers.ModelSerializer):
    registration_date = serializers.DateTimeField(source="created_at", read_only=True)
    active_memberships = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()
    class_count = serializers.SerializerMethodField()
    active_staff_count = serializers.SerializerMethodField()
    onboarding = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = ("id", "name", "slug", "contact_email", "contact_phone", "school_type", "country", "state", "local_government_area", "verification_status", "verification_reason", "verified_at", "registration_date", "is_active", "active_memberships", "student_count", "class_count", "active_staff_count", "onboarding")

    def _usage(self, obj):
        if not hasattr(obj, "_platform_usage"):
            obj._platform_usage = {
                "active_memberships": obj.memberships.filter(is_active=True).count(),
                "student_count": Student.objects.filter(school=obj).count(),
                "class_count": ClassLevel.objects.filter(school=obj).count(),
                "active_staff_count": StaffProfile.objects.filter(school=obj, status=StaffProfile.Status.ACTIVE).count(),
            }
        return obj._platform_usage

    def get_active_memberships(self, obj): return self._usage(obj)["active_memberships"]
    def get_student_count(self, obj): return self._usage(obj)["student_count"]
    def get_class_count(self, obj): return self._usage(obj)["class_count"]
    def get_active_staff_count(self, obj): return self._usage(obj)["active_staff_count"]

    def get_onboarding(self, obj):
        try:
            progress = obj.onboarding_progress
        except SchoolOnboardingProgress.DoesNotExist:
            progress = None
        return {"current_step": progress.current_step if progress else 1, "updated_at": progress.updated_at if progress else None}


class SchoolVerificationEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = SchoolVerificationEvent
        fields = ("id", "school", "school_name", "actor", "actor_email", "action", "from_status", "to_status", "reason", "metadata", "created_at")


class PlatformSchoolsView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        schools = School.objects.all().select_related("onboarding_progress").order_by("-created_at", "-pk")
        search = request.query_params.get("q", "").strip()
        verification_status = request.query_params.get("status", "").strip()
        if search:
            from django.db.models import Q
            schools = schools.filter(Q(name__icontains=search) | Q(contact_email__icontains=search) | Q(state__icontains=search) | Q(local_government_area__icontains=search))
        if verification_status in School.VerificationStatus.values:
            schools = schools.filter(verification_status=verification_status)
        paginator = PlatformSchoolPagination()
        page = paginator.paginate_queryset(schools, request, view=self)
        return paginator.get_paginated_response(PlatformSchoolSerializer(page, many=True).data)


class PlatformSchoolDetailView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, pk, **kwargs):
        school = School.objects.select_related("onboarding_progress").filter(pk=pk).first()
        if school is None:
            return Response({"detail": "School not found."}, status=404)
        data = PlatformSchoolSerializer(school).data
        data["profile"] = SchoolProfileSerializer(school).data
        data["events"] = SchoolVerificationEventSerializer(school.verification_events.select_related("actor", "school")[:50], many=True).data
        return Response(data)


class PlatformSchoolActionView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def post(self, request, pk, action, **kwargs):
        allowed = {"review", "verify", "reject", "suspend", "reactivate"}
        if action not in allowed:
            return Response({"detail": "Unknown school review action."}, status=404)
        reason = serializers.CharField(required=False, allow_blank=True, max_length=2000).run_validation(request.data.get("reason", ""))
        if action in {"reject", "suspend", "reactivate"} and not reason.strip():
            return Response({"reason": ["A reason is required for this action."]}, status=400)
        school = School.objects.filter(pk=pk).first()
        if school is None:
            return Response({"detail": "School not found."}, status=404)
        transition = {
            "review": School.VerificationStatus.UNDER_REVIEW,
            "verify": School.VerificationStatus.VERIFIED,
            "reject": School.VerificationStatus.REJECTED,
            "suspend": School.VerificationStatus.SUSPENDED,
            "reactivate": School.VerificationStatus.UNDER_REVIEW,
        }[action]
        current = school.verification_status
        if action == "review" and current not in {School.VerificationStatus.PENDING, School.VerificationStatus.REJECTED}:
            return Response({"detail": "Only pending or rejected schools can enter review."}, status=400)
        if action == "verify" and current not in {School.VerificationStatus.PENDING, School.VerificationStatus.UNDER_REVIEW}:
            return Response({"detail": "Only pending or reviewed schools can be verified."}, status=400)
        if action == "reject" and current not in {School.VerificationStatus.PENDING, School.VerificationStatus.UNDER_REVIEW}:
            return Response({"detail": "Only pending or reviewed schools can be rejected."}, status=400)
        if action == "suspend" and current == School.VerificationStatus.SUSPENDED:
            return Response({"detail": "This school is already suspended."}, status=400)
        if action == "reactivate" and current != School.VerificationStatus.SUSPENDED:
            return Response({"detail": "Only suspended schools can be reactivated."}, status=400)
        with transaction.atomic():
            school.verification_status = transition
            school.verification_reason = reason.strip() if action in {"reject", "suspend", "reactivate"} else ""
            school.verified_at = timezone.now() if action == "verify" else None if action in {"suspend", "reject", "reactivate"} else school.verified_at
            school.save(update_fields=("verification_status", "verification_reason", "verified_at", "updated_at"))
            SchoolVerificationEvent.objects.create(school=school, actor=request.user, action=action, from_status=current, to_status=transition, reason=reason.strip())
        return Response(PlatformSchoolSerializer(school).data)
