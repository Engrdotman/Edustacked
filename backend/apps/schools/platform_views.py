from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassLevel
from apps.billing.models import CreditPayment
from apps.staff.models import StaffProfile
from apps.students.models import Student
from .models import PlatformUserAccessEvent, School, SchoolMembership, SchoolOnboardingProgress, SchoolVerificationEvent
from .permissions import IsPlatformSuperadmin
from .serializers import SchoolProfileSerializer


class PlatformSchoolPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class PlatformUserPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "overview": getattr(self, "overview", {}),
            "results": data,
        })


def platform_overview():
    """Return platform counts and verified money received from credit purchases."""
    User = get_user_model()
    payments = CreditPayment.objects.filter(
        status=CreditPayment.Status.SUCCESS,
        verified_at__isnull=False,
    )
    revenue = payments.values("currency").annotate(
        amount_minor=Sum("amount_minor"),
        payment_count=Count("id"),
    ).order_by("currency")
    school_purchases = payments.values("school_id", "school__name", "currency").annotate(
        amount_minor=Sum("amount_minor"),
        payment_count=Count("id"),
    ).order_by("-amount_minor", "school__name")[:10]
    schools = School.objects.all()
    return {
        "users_total": User.objects.count(),
        "users_active": User.objects.filter(is_active=True).count(),
        "users_inactive": User.objects.filter(is_active=False).count(),
        "schools_total": schools.count(),
        "schools_verified": schools.filter(verification_status=School.VerificationStatus.VERIFIED).count(),
        "schools_pending": schools.filter(verification_status=School.VerificationStatus.PENDING).count(),
        "schools_suspended": schools.filter(verification_status=School.VerificationStatus.SUSPENDED).count(),
        "credit_purchase_count": payments.count(),
        "schools_with_credit_purchases": payments.values("school_id").distinct().count(),
        "verified_revenue": list(revenue),
        "top_credit_purchasers": list(school_purchases),
    }


class PlatformUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()
    latest_platform_action = serializers.SerializerMethodField()
    can_reactivate = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ("id", "email", "first_name", "last_name", "full_name", "is_active", "is_superuser", "created_at", "memberships", "latest_platform_action", "can_reactivate")

    def get_full_name(self, obj):
        return obj.get_full_name().strip()

    def get_memberships(self, obj):
        rows = getattr(obj, "_platform_memberships", None)
        if rows is None:
            rows = obj.school_memberships.select_related("school").all()
        return [{
            "school_id": row.school_id,
            "school_name": row.school.name,
            "role": row.role,
            "is_active": row.is_active,
        } for row in rows]

    def get_latest_platform_action(self, obj):
        events = getattr(obj, "_platform_access_events", None)
        event = events[0] if events else None
        if event is None:
            return None
        return {
            "action": event.action,
            "reason": event.reason,
            "created_at": event.created_at,
            "actor_email": event.actor.email,
        }

    def get_can_reactivate(self, obj):
        events = getattr(obj, "_platform_access_events", None)
        return bool(not obj.is_active and events and events[0].action == PlatformUserAccessEvent.Action.SUSPEND)


class PlatformUsersView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        User = get_user_model()
        users = User.objects.all().prefetch_related(
            Prefetch("school_memberships", queryset=SchoolMembership.objects.select_related("school"), to_attr="_platform_memberships"),
            Prefetch("platform_access_events", queryset=PlatformUserAccessEvent.objects.select_related("actor").order_by("-created_at", "-pk"), to_attr="_platform_access_events"),
        ).order_by("-created_at", "-pk")
        query = request.query_params.get("q", "").strip()
        account_status = request.query_params.get("status", "").strip()
        if query:
            users = users.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query))
        if account_status == "active":
            users = users.filter(is_active=True)
        elif account_status == "inactive":
            users = users.filter(is_active=False)
        paginator = PlatformUserPagination()
        paginator.overview = platform_overview()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(PlatformUserSerializer(page, many=True).data)


class PlatformUserActionView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def post(self, request, pk, action, **kwargs):
        if action not in {"suspend", "reactivate"}:
            return Response({"detail": "Unknown account action."}, status=status.HTTP_404_NOT_FOUND)
        reason = serializers.CharField(required=True, allow_blank=False, max_length=2000).run_validation(request.data.get("reason", ""))
        User = get_user_model()
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=pk).first()
            if user is None:
                return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
            if user.is_superuser:
                return Response({"detail": "Platform administrator accounts cannot be suspended here."}, status=status.HTTP_400_BAD_REQUEST)
            if user.pk == request.user.pk:
                return Response({"detail": "You cannot suspend your own platform account."}, status=status.HTTP_400_BAD_REQUEST)
            latest_event = PlatformUserAccessEvent.objects.filter(target_user=user).order_by("-created_at", "-pk").first()
            if action == "suspend":
                if not user.is_active:
                    return Response({"detail": "This account is already inactive."}, status=status.HTTP_400_BAD_REQUEST)
                user.is_active = False
                user.save(update_fields=("is_active",))
                event_action = PlatformUserAccessEvent.Action.SUSPEND
            else:
                if user.is_active or not latest_event or latest_event.action != PlatformUserAccessEvent.Action.SUSPEND:
                    return Response({"detail": "This account has no active platform suspension to remove."}, status=status.HTTP_400_BAD_REQUEST)
                user.is_active = True
                user.save(update_fields=("is_active",))
                event_action = PlatformUserAccessEvent.Action.REACTIVATE
            PlatformUserAccessEvent.objects.create(target_user=user, actor=request.user, action=event_action, reason=reason.strip())
        return Response({"detail": "Account suspended successfully." if action == "suspend" else "Account reactivated successfully.", "user_id": user.pk, "is_active": user.is_active})


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
            if action == "suspend":
                school.is_active = False
            elif action == "reactivate":
                school.is_active = True
            school.save(update_fields=("verification_status", "verification_reason", "verified_at", "is_active", "updated_at"))
            SchoolVerificationEvent.objects.create(school=school, actor=request.user, action=action, from_status=current, to_status=transition, reason=reason.strip())
        return Response(PlatformSchoolSerializer(school).data)
