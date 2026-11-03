from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.signing import BadSignature
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.schools.models import School, SchoolMembership

from .models import ServiceEntitlement, ServicePlan, verify_offline_license
from .services import service_is_active


User = get_user_model()


@override_settings(CBT_LICENSE_SIGNING_KEY="unit-test-license-key")
class ServiceEntitlementTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School")
        self.other_school = School.objects.create(name="South School")
        self.admin = User.objects.create_user(username="north-admin", email="north@example.test", password="test-pass")
        self.other_admin = User.objects.create_user(username="south-admin", email="south@example.test", password="test-pass")
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.other_admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client = APIClient()

    def _entitlement(self, school=None, **overrides):
        today = timezone.localdate()
        values = {
            "school": school or self.school,
            "service_code": "offline_cbt",
            "package_type": "school",
            "student_capacity": 100,
            "starts_on": today - timedelta(days=1),
            "expires_on": today + timedelta(days=30),
        }
        values.update(overrides)
        return ServiceEntitlement.objects.create(**values)

    def test_school_can_only_see_its_own_entitlements(self):
        own = self._entitlement()
        self._entitlement(school=self.other_school)
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/services/entitlements/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [str(own.id)])
        self.assertNotIn("signed_license", response.data[0])

    def test_offline_license_signature_and_grace_window_are_validated(self):
        entitlement = self._entitlement(
            starts_on=timezone.localdate() - timedelta(days=10),
            expires_on=timezone.localdate() - timedelta(days=2),
            offline_grace_days=3,
        )
        payload = verify_offline_license(entitlement.signed_license)
        self.assertTrue(payload["valid_for_offline_use"])
        self.assertTrue(payload["grace_period"])
        with self.assertRaises(BadSignature):
            verify_offline_license(entitlement.signed_license + "tampered")

    def test_expiry_and_status_control_central_service_access(self):
        entitlement = self._entitlement()
        self.assertTrue(service_is_active(self.school, "offline_cbt"))
        entitlement.status = ServiceEntitlement.Status.SUSPENDED
        entitlement.save()
        self.assertFalse(service_is_active(self.school, "offline_cbt"))

    def test_plan_is_independent_of_credit_billing_and_tenant_isolation(self):
        plan = ServicePlan.objects.create(
            service_code="offline_cbt", name="CBT School", package_type="school",
            student_capacity=100, price_minor=5000000,
        )
        self.assertEqual(plan.price_minor, 5000000)
        self.assertFalse(service_is_active(self.school, "offline_cbt"))
        self.client.force_authenticate(self.other_admin)
        response = self.client.get("/api/v1/services/plans/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        self.assertEqual(response.status_code, 403)

    def test_platform_entitlement_grant_endpoint_is_superuser_only(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/v1/platform/services/entitlements/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_issue_a_signed_grant_without_returning_license_secret(self):
        platform_admin = User.objects.create_superuser(username="platform", email="platform@example.test", password="test-pass")
        self.client.force_authenticate(platform_admin)
        today = timezone.localdate()
        response = self.client.post("/api/v1/platform/services/entitlements/", {
            "school": self.school.pk,
            "service_code": "offline_cbt",
            "package_type": "school",
            "student_capacity": 100,
            "starts_on": today.isoformat(),
            "expires_on": (today + timedelta(days=365)).isoformat(),
            "payment_reference": "verified-qa-payment-1",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        entitlement = ServiceEntitlement.objects.get(license_id=response.data["license_id"])
        self.assertTrue(entitlement.signed_license)
        self.assertNotIn("signed_license", response.data)
        self.assertTrue(verify_offline_license(entitlement.signed_license)["valid_for_offline_use"])

    def test_core_report_card_credit_endpoint_is_independent_of_cbt_entitlement(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/billing/credits/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["balance"], 0)
