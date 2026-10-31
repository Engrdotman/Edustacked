from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import School, SchoolMembership, SchoolVerificationEvent

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolOnboardingLifecycleApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Sunrise Academy", slug="sunrise-academy", state="Lagos",
            local_government_area="Ikeja", address="School Road", contact_phone="+2348012345678",
        )
        self.owner = User.objects.create_user(
            username="sunrise-owner", email="owner@sunrise.test", password="Owner-Strong-Password-823!",
        )
        self.membership = SchoolMembership.objects.create(
            user=self.owner, school=self.school, role=SchoolMembership.Role.SCHOOL_OWNER,
        )
        self.principal = User.objects.create_user(
            username="sunrise-principal", email="principal@sunrise.test", password="Principal-Strong-Password-418!",
        )
        self.principal_membership = SchoolMembership.objects.create(
            user=self.principal, school=self.school, role=SchoolMembership.Role.PRINCIPAL,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.client.credentials(HTTP_X_SCHOOL_ID=str(self.school.pk))

    def test_pending_school_can_save_and_resume_onboarding_progress(self):
        response = self.client.get("/api/v1/schools/onboarding/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["school_status"], School.VerificationStatus.PENDING)
        self.assertEqual(len(response.data["steps"]), 5)
        saved = self.client.patch("/api/v1/schools/onboarding/", {"current_step": 4}, format="json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["current_step"], 4)
        self.school.onboarding_progress.refresh_from_db()
        self.assertEqual(self.school.onboarding_progress.current_step, 4)

    @override_settings(SCHOOL_VERIFIED_REQUIRED_CAPABILITIES=frozenset({"integrations.manage"}))
    def test_pending_school_is_allowed_basic_access_but_verified_capability_is_gated(self):
        response = self.client.get("/api/v1/schools/profile/")
        self.assertEqual(response.status_code, 200)
        from rest_framework.permissions import IsAuthenticated
        from rest_framework.response import Response
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework.views import APIView
        from .permissions import HasSchoolPermission

        class IntegrationGate(APIView):
            permission_classes = (IsAuthenticated, HasSchoolPermission)
            required_school_permission = "integrations.manage"

            def get(self, request):
                return Response({"allowed": True})

        factory = APIRequestFactory()
        request = factory.get("/api/v1/probe/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        force_authenticate(request, user=self.owner)
        denied = IntegrationGate.as_view()(request)
        self.assertEqual(denied.status_code, 403)
        self.school.verification_status = School.VerificationStatus.VERIFIED
        self.school.save(update_fields=("verification_status",))
        request = factory.get("/api/v1/probe/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        force_authenticate(request, user=self.owner)
        allowed = IntegrationGate.as_view()(request)
        self.assertEqual(allowed.status_code, 200)

    def test_ownership_transfer_requires_owner_password_and_creates_audit_record(self):
        url = f"/api/v1/schools/{self.school.pk}/ownership/transfer/"
        invalid = self.client.post(url, {"target_membership_id": self.principal_membership.pk, "password": "wrong", "reason": "Retirement"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        success = self.client.post(url, {"target_membership_id": self.principal_membership.pk, "password": "Owner-Strong-Password-823!", "reason": "Ownership transition"}, format="json")
        self.assertEqual(success.status_code, 200)
        self.membership.refresh_from_db()
        self.principal_membership.refresh_from_db()
        self.assertEqual(self.membership.role, SchoolMembership.Role.SCHOOL_ADMIN)
        self.assertEqual(self.principal_membership.role, SchoolMembership.Role.SCHOOL_OWNER)
        event = SchoolVerificationEvent.objects.get(action="ownership_transferred")
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.metadata["new_owner_id"], self.principal.pk)

    def test_only_platform_superadmin_can_review_and_suspend_schools_with_audit(self):
        list_url = "/api/v1/schools/platform/schools/"
        denied = self.client.get(list_url)
        self.assertEqual(denied.status_code, 403)
        platform_admin = User.objects.create_superuser(username="platform-root", email="root@platform.test", password="Platform-Strong-Password-105!")
        admin_client = APIClient()
        admin_client.force_authenticate(platform_admin)
        detail_url = f"{list_url}{self.school.pk}/"
        verified = admin_client.post(f"{detail_url}verify/", {}, format="json")
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["verification_status"], School.VerificationStatus.VERIFIED)
        suspended = admin_client.post(f"{detail_url}suspend/", {"reason": "Identity review required."}, format="json")
        self.assertEqual(suspended.status_code, 200)
        self.assertEqual(suspended.data["verification_status"], School.VerificationStatus.SUSPENDED)
        self.assertEqual(SchoolVerificationEvent.objects.filter(school=self.school).count(), 2)
        self.assertEqual(SchoolVerificationEvent.objects.filter(action="suspend").get().reason, "Identity review required.")
        self.client.credentials(HTTP_X_SCHOOL_ID=str(self.school.pk))
        suspended_access = self.client.get("/api/v1/schools/profile/")
        self.assertEqual(suspended_access.status_code, 403)
        reactivated = admin_client.post(f"{detail_url}reactivate/", {"reason": "Documents received."}, format="json")
        self.assertEqual(reactivated.data["verification_status"], School.VerificationStatus.UNDER_REVIEW)
        self.assertEqual(SchoolVerificationEvent.objects.filter(school=self.school).count(), 3)

    def test_reject_requires_a_reason_and_preserves_school_history(self):
        admin = User.objects.create_superuser(username="platform-reviewer", email="reviewer@platform.test", password="Platform-Strong-Password-914!")
        admin_client = APIClient()
        admin_client.force_authenticate(admin)
        url = f"/api/v1/schools/platform/schools/{self.school.pk}/reject/"
        missing_reason = admin_client.post(url, {}, format="json")
        self.assertEqual(missing_reason.status_code, 400)
        rejected = admin_client.post(url, {"reason": "Please provide the school registration certificate."}, format="json")
        self.assertEqual(rejected.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.verification_status, School.VerificationStatus.REJECTED)
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())
        self.assertEqual(self.school.verification_events.get().reason, "Please provide the school registration certificate.")
