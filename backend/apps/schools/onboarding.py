from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Subject, Term
from apps.staff.models import StaffProfile
from .models import SchoolMembership, SchoolOnboardingProgress
from .permissions import HasSchoolPermission, authorized_membership
from .tenancy import resolve_authorized_school


class OnboardingStepSerializer(serializers.Serializer):
    current_step = serializers.IntegerField(min_value=1, max_value=5)


def onboarding_summary(school, progress):
    has_profile = bool(school.address.strip() and school.contact_phone.strip() and school.state.strip() and school.local_government_area.strip())
    has_academics = AcademicSession.objects.filter(school=school).exists() and Term.objects.filter(school=school).exists()
    has_structure = ClassLevel.objects.filter(school=school).exists() and ClassArm.objects.filter(school=school).exists() and Subject.objects.filter(school=school).exists()
    has_staff = StaffProfile.objects.filter(school=school).exists() or SchoolMembership.objects.filter(school=school, is_active=True).count() > 1
    steps = [
        {"id": 1, "key": "school_profile", "label": "Complete school profile", "completed": has_profile, "path": "/app/school"},
        {"id": 2, "key": "academic_setup", "label": "Create an academic session and term", "completed": has_academics, "path": "/app/academics"},
        {"id": 3, "key": "academic_structure", "label": "Add classes, arms, and subjects", "completed": has_structure, "path": "/app/academics"},
        {"id": 4, "key": "invite_staff", "label": "Add staff and teachers", "completed": has_staff, "path": "/app/staff"},
        {"id": 5, "key": "review", "label": "Review your setup", "completed": all((has_profile, has_academics, has_structure, has_staff)), "path": "/app"},
    ]
    completed = sum(step["completed"] for step in steps[:4])
    return {
        "current_step": progress.current_step,
        "completed_steps": completed,
        "total_steps": 4,
        "percentage": round(completed * 100 / 4),
        "steps": steps,
        "school_status": school.verification_status,
        "verification_reason": school.verification_reason,
        "can_continue": school.verification_status != school.VerificationStatus.SUSPENDED,
    }


class SchoolOnboardingView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "school.view"

    def school(self, request):
        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))

    def get(self, request, **kwargs):
        school = self.school(request)
        progress, _ = SchoolOnboardingProgress.objects.get_or_create(school=school)
        return Response(onboarding_summary(school, progress))

    def patch(self, request, **kwargs):
        school = self.school(request)
        membership = None if request.user.is_superuser else authorized_membership(request.user, request, self)
        if membership and membership.role not in {
            SchoolMembership.Role.SCHOOL_OWNER, SchoolMembership.Role.SCHOOL_ADMIN,
            SchoolMembership.Role.SCHOOL_MANAGER, SchoolMembership.Role.PRINCIPAL,
        }:
            return Response({"detail": "You do not have permission to save onboarding progress."}, status=403)
        serializer = OnboardingStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        progress, _ = SchoolOnboardingProgress.objects.get_or_create(school=school)
        progress.current_step = serializer.validated_data["current_step"]
        progress.updated_by = request.user
        progress.save(update_fields=("current_step", "updated_by", "updated_at"))
        return Response(onboarding_summary(school, progress))


class OwnershipTransferSerializer(serializers.Serializer):
    target_membership_id = serializers.IntegerField(min_value=1)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)
