import hashlib
import hmac
import json
import re
from io import BytesIO
from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.models import School, SchoolMembership
from apps.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

from .models import FeeCharge, FeeLedgerEntry, FeeNotification, FeePaymentAllocation, FeeSchedule, PaymentProviderEvent, ReceiptOtpChallenge, SchoolFeePayment, SchoolFeeSettings
from .providers import FlutterwaveSchoolProvider
from .services import issue_fee_schedule, issue_receipt_otp_to_guardians, record_physical_payment, verify_receipt_otp
from .views import public_payment

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolFeesApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Northside Academy", slug="northside-academy", contact_email="office@northside.example", contact_phone="08030000000", address="12 School Road")
        self.other_school = School.objects.create(name="Southside Academy", slug="southside-academy")
        self.admin = self.make_user("fees-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.accountant = self.make_user("fees-accountant", SchoolMembership.Role.ACCOUNTANT, self.school)
        self.teacher = self.make_user("fees-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.other_admin = self.make_user("fees-other", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.parent = User.objects.create_user(username="fees-parent", email="parent@example.test", password="pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status=AcademicSession.Status.ACTIVE)
        self.session.refresh_from_db()
        self.term = Term.objects.create(school=self.school, academic_session=self.session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.student = self.make_student("FEE-001", "Amina")
        self.guardian = Guardian.objects.create(school=self.school, user=self.parent, full_name="Parent One", phone="08030000001", email=self.parent.email)
        StudentGuardian.objects.create(school=self.school, student=self.student, guardian=self.guardian, relationship_type="Parent", is_primary_contact=True, can_receive_communications=True)

    @staticmethod
    def make_user(username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def make_student(self, admission, first_name):
        student = Student.objects.create(school=self.school, admission_number=admission, first_name=first_name, last_name="Student")
        StudentEnrollment.objects.create(school=self.school, student=student, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        return student

    def api(self, method, path, data=None, *, school=None, user=None, format="json", **headers):
        self.client.force_authenticate(user or self.admin)
        return getattr(self.client, method)(path, data, format=format, HTTP_X_SCHOOL_ID=str((school or self.school).pk), **headers)

    def create_schedule(self, amount=100_000, category="Tuition"):
        response = self.api("post", "/api/v1/school-fees/schedules/", {
            "academic_session": self.session.pk, "term": self.term.pk,
            "class_level": self.level.pk, "category": category,
            "amount_minor": amount,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return FeeSchedule.objects.get(pk=response.data["id"])

    def record_manual(self, charge, amount, *, user=None):
        return self.api("post", "/api/v1/school-fees/payments/manual/", {
            "amount_minor": amount, "method": "cash", "description": "Resumption payment",
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": amount}],
        }, user=user)

    def configure_online(self, provider="paystack"):
        return SchoolFeeSettings.objects.create(
            school=self.school, bank_name="Test Bank", bank_code="058", account_name="Northside Academy",
            account_number="0123456789", account_status=SchoolFeeSettings.AccountStatus.VERIFIED,
            account_verified_name="Northside Academy", provider=provider,
            provider_account_id="ACCT_school_account", online_enabled=True,
        )

    def test_schedule_issues_only_active_same_class_enrollments_and_is_idempotent(self):
        other_class = ClassLevel.objects.create(school=self.school, name="JSS 2", code="JSS2")
        other_arm = ClassArm.objects.create(school=self.school, class_level=other_class, name="A")
        other_student = Student.objects.create(school=self.school, admission_number="FEE-002", first_name="Bola", last_name="Student")
        StudentEnrollment.objects.create(school=self.school, student=other_student, academic_session=self.session, class_level=other_class, class_arm=other_arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        schedule = self.create_schedule()
        self.assertEqual(schedule.charges.count(), 1)
        self.assertEqual(schedule.charges.get().student, self.student)
        issued_again = self.api("post", "/api/v1/school-fees/schedules/issue/", {"schedule_id": schedule.pk})
        self.assertEqual(issued_again.status_code, status.HTTP_200_OK, issued_again.data)
        self.assertEqual(issued_again.data["issued_students"], 0)
        self.assertEqual(FeeLedgerEntry.objects.filter(kind=FeeLedgerEntry.Kind.CHARGE).count(), 1)

    def test_physical_partial_full_and_excess_credit_share_immutable_ledger(self):
        schedule = self.create_schedule()
        charge = schedule.charges.get()
        partial = self.record_manual(charge, 40_000)
        self.assertEqual(partial.status_code, status.HTTP_201_CREATED, partial.data)
        charge.refresh_from_db()
        self.assertEqual(charge.ledger_entries.aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount_minor"))["total"], 60_000)
        self.assertEqual(partial.data["channel"], SchoolFeePayment.Channel.PHYSICAL)
        self.assertEqual(partial.data["status"], SchoolFeePayment.Status.SUCCESS)
        self.assertTrue(FeePaymentAllocation.objects.filter(payment__reference=partial.data["reference"]).exists())
        with self.assertRaises(ValidationError):
            charge.ledger_entries.first().delete()
        payment = self.record_manual(charge, 100_000)
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED, payment.data)
        self.assertEqual(charge_balance_value(charge), 0)
        self.assertEqual(payment.data["allocations"][0]["amount_minor"], 60_000)
        self.assertTrue(FeePaymentAllocation.objects.filter(payment__reference=payment.data["reference"], fee_charge__isnull=True, amount_minor=40_000).exists())

    def test_one_payment_can_be_allocated_to_more_than_one_child(self):
        first_charge = self.create_schedule().charges.get()
        second_student = self.make_student("FEE-003", "Tomi")
        issue_fee_schedule(first_charge.fee_schedule, self.admin)
        second_charge = FeeCharge.objects.get(fee_schedule=first_charge.fee_schedule, student=second_student)
        response = self.api("post", "/api/v1/school-fees/payments/manual/", {
            "amount_minor": 50_000, "method": "bank_transfer",
            "allocations": [
                {"fee_charge_id": first_charge.pk, "amount_minor": 20_000},
                {"fee_charge_id": second_charge.pk, "amount_minor": 30_000},
            ],
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["allocations"][0]["student_id"], self.student.pk)
        self.assertEqual(response.data["allocations"][1]["student_id"], second_student.pk)
        self.assertEqual(FeeLedgerEntry.objects.filter(payment__reference=response.data["reference"], kind=FeeLedgerEntry.Kind.PAYMENT).count(), 2)

    def test_parent_payment_view_only_discloses_allocations_for_linked_children(self):
        first_charge = self.create_schedule().charges.get()
        second_student = self.make_student("FEE-004", "Tomi")
        issue_fee_schedule(first_charge.fee_schedule, self.admin)
        second_charge = FeeCharge.objects.get(fee_schedule=first_charge.fee_schedule, student=second_student)
        other_parent = User.objects.create_user(username="fees-parent-two", email="parent.two@example.test", password="pass12345")
        other_guardian = Guardian.objects.create(school=self.school, user=other_parent, full_name="Parent Two", phone="08030000002")
        StudentGuardian.objects.create(school=self.school, student=second_student, guardian=other_guardian, relationship_type="Parent", is_primary_contact=True, can_receive_communications=True)
        payment = SchoolFeePayment.objects.create(
            school=self.school, channel=SchoolFeePayment.Channel.ONLINE, method=SchoolFeePayment.Method.CARD,
            reference="EDUF-PRIVACY-CHECK", amount_minor=50_000, status=SchoolFeePayment.Status.SUCCESS,
        )
        from apps.school_fees.services import _write_allocations
        _write_allocations(payment, [
            {"fee_charge_id": first_charge.pk, "amount_minor": 20_000},
            {"fee_charge_id": second_charge.pk, "amount_minor": 30_000},
        ], self.admin)
        visible = public_payment(payment, student_ids={self.student.pk})
        self.assertEqual(visible["amount_minor"], 20_000)
        self.assertEqual([item["student_id"] for item in visible["allocations"]], [self.student.pk])

    def test_accountant_can_record_teacher_cannot_and_cross_school_is_hidden(self):
        charge = self.create_schedule().charges.get()
        allowed = self.record_manual(charge, 25_000, user=self.accountant)
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED, allowed.data)
        denied = self.api("post", "/api/v1/school-fees/payments/manual/", {"amount_minor": 10_000, "method": "cash", "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 10_000}]}, user=self.teacher)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        foreign = self.api("get", "/api/v1/school-fees/charges/", school=self.other_school, user=self.other_admin)
        self.assertEqual(foreign.status_code, status.HTTP_200_OK)
        self.assertEqual(foreign.data["results"], [])

    @patch("apps.school_fees.views.provider_for")
    def test_school_account_connection_verifies_account_and_keeps_number_masked(self, provider_for_mock):
        provider = Mock()
        provider.connect_account.return_value = {"account_name": "NORTHSIDE ACADEMY", "provider_account_id": "ACCT_123"}
        provider_for_mock.return_value = provider
        response = self.api("post", "/api/v1/school-fees/settings/connect/", {
            "provider": "paystack", "bank_code": "058", "bank_name": "Test Bank",
            "account_number": "0123456789", "account_type": "Current", "business_mobile": "08030000000",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = SchoolFeeSettings.objects.get(school=self.school)
        self.assertTrue(row.online_enabled)
        self.assertEqual(row.provider_account_id, "ACCT_123")
        self.assertEqual(response.data["settings"]["account_number"], "••••6789")
        provider.connect_account.assert_called_once()

    @override_settings(FRONTEND_BASE_URL="https://edustacked.example")
    @patch("apps.billing.providers.BachsProvider.connect_capabilities", return_value=set())
    def test_bachs_connect_is_disabled_until_eduStacked_platform_is_approved(self, connect_capabilities):
        response = self.api("post", "/api/v1/school-fees/settings/bachs-connect/", {
            "contact_email": "owner@northside.example", "entity_type": "company",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("Connect is not enabled", str(response.data))
        connect_capabilities.assert_called_once()

    @override_settings(BACHS_WEBHOOK_SECRET="bachs-fee-hook")
    @patch("apps.billing.views.BachsProvider.verify")
    @patch("apps.school_fees.views.provider_for")
    def test_bachs_direct_fee_checkout_and_webhook_credit_only_after_server_verification(self, provider_for_mock, verify):
        self.configure_online(provider="bachs")
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {
            "authorization_url": "https://checkout.bachs.io/c/fee-test", "checkout_id": "chk-fee-test",
        }
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 25_000}],
        }, user=self.parent)
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        payment = SchoolFeePayment.objects.get(reference=initialized.data["reference"])
        self.assertEqual(payment.provider_metadata["checkout_id"], "chk-fee-test")
        self.assertEqual(payment.provider_metadata["provider_account_id"], "ACCT_school_account")
        provider.initialize.assert_called_once()
        self.assertEqual(provider.initialize.call_args.kwargs["connected_account_id"], "ACCT_school_account")

        verify.return_value = {
            "id": "charge-fee-test", "reference": payment.reference, "status": "success",
            "amount": payment.amount_minor, "currency": payment.currency, "channel": "card",
        }
        event = {"id": "evt-fee-test", "type": "checkout.completed", "account": "ACCT_school_account", "data": {
            "checkout_id": "chk-fee-test", "reference": payment.reference,
            "status": "completed", "payment_status": "paid", "amount": "250.00", "currency": "NGN",
        }}
        raw = json.dumps(event, separators=(",", ":")).encode()
        timestamp = str(int(__import__("time").time()))
        signature = hmac.new(b"bachs-fee-hook", f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
        self.client.force_authenticate(user=None)
        accepted = self.client.generic(
            "POST", "/api/v1/billing/bachs/webhook/", raw, content_type="application/json",
            HTTP_X_BACHS_SIGNATURE_V2=f"t={timestamp},v1={signature}",
        )
        repeated = self.client.generic(
            "POST", "/api/v1/billing/bachs/webhook/", raw, content_type="application/json",
            HTTP_X_BACHS_SIGNATURE_V2=f"t={timestamp},v1={signature}",
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK, repeated.data)
        verify.assert_called_once_with("chk-fee-test", connected_account_id="ACCT_school_account")
        payment.refresh_from_db()
        self.assertEqual(payment.status, SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(payment.ledger_entries.filter(kind=FeeLedgerEntry.Kind.PAYMENT).count(), 1)

    @patch("apps.school_fees.views.provider_for")
    def test_parent_can_start_online_payment_only_for_linked_student_and_backend_price(self, provider_for_mock):
        setting = self.configure_online()
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider_for_mock.return_value = provider
        response = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 30_000}],
        }, user=self.parent)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["amount_minor"], 30_000)
        provider.initialize.assert_called_once()
        payment = SchoolFeePayment.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.provider_metadata["subaccount_id"], setting.provider_account_id)
        other_student = self.make_student("FEE-999", "Wrong")
        foreign_charge = FeeCharge.objects.create(school=self.school, fee_schedule=charge.fee_schedule, student=other_student, enrollment=other_student.enrollments.get(), amount_minor=charge.amount_minor, created_by=self.admin)
        denied = self.api("post", "/api/v1/parent/fees/payments/initialize/", {"allocations": [{"fee_charge_id": foreign_charge.pk, "amount_minor": 1_000}]}, user=self.parent)
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        FRONTEND_BASE_URL="https://school.example.test",
    )
    @patch("apps.school_fees.views.provider_for")
    def test_invited_parent_can_activate_login_and_pay_with_backend_verified_checkout(self, provider_for_mock):
        """Exercise the parent path end to end while keeping the provider mocked."""
        self.configure_online()
        charge = self.create_schedule(amount=100_000).charges.get()
        invited_guardian = Guardian.objects.create(
            school=self.school, full_name="Amina's Parent", phone="08030000002",
            email="amina-parent@example.test",
        )
        link = StudentGuardian.objects.create(
            school=self.school, student=self.student, guardian=invited_guardian,
            relationship_type="Parent", is_primary_contact=False,
            can_receive_communications=True,
        )

        invitation_response = self.api(
            "post", f"/api/v1/parent/staff/students/{self.student.pk}/guardians/{link.pk}/invite/", {},
        )
        self.assertEqual(invitation_response.status_code, status.HTTP_202_ACCEPTED, invitation_response.data)
        token_match = re.search(r"token=([^\s]+)", mail.outbox[-1].body)
        self.assertIsNotNone(token_match, "The invitation email should contain a one-time activation link.")

        self.client.force_authenticate(user=None)
        activated = self.client.post(
            "/api/v1/guardian/activate/",
            {"token": token_match.group(1), "password": "Strong-Parent-Password-42!"},
            format="json",
        )
        self.assertEqual(activated.status_code, status.HTTP_200_OK, activated.data)
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": invited_guardian.email, "password": "Strong-Parent-Password-42!", "portal": "parent"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        students = self.client.get("/api/v1/parent/students/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        self.assertEqual(students.status_code, status.HTTP_200_OK, students.data)
        self.assertEqual([row["id"] for row in students.data], [self.student.pk])
        fees = self.client.get(
            f"/api/v1/parent/students/{self.student.pk}/fees/",
            HTTP_X_SCHOOL_ID=str(self.school.pk),
        )
        self.assertEqual(fees.status_code, status.HTTP_200_OK, fees.data)
        self.assertEqual(fees.data["charges"][0]["outstanding_minor"], 100_000)

        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/parent-fee"}
        provider.verify.return_value = {
            "reference": "", "status": "success", "amount": 25_000,
            "currency": "NGN", "id": "parent-e2e-test", "channel": "card",
        }
        provider_for_mock.return_value = provider
        initialized = self.client.post(
            "/api/v1/parent/fees/payments/initialize/",
            {"allocations": [{"fee_charge_id": charge.pk, "amount_minor": 25_000}]},
            format="json", HTTP_X_SCHOOL_ID=str(self.school.pk),
        )
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        self.assertEqual(initialized.data["amount_minor"], 25_000)
        payment = SchoolFeePayment.objects.get(reference=initialized.data["reference"])
        provider.verify.return_value["reference"] = payment.reference
        confirmed = self.client.post(
            f"/api/v1/parent/fees/payments/{payment.reference}/", {},
            format="json", HTTP_X_SCHOOL_ID=str(self.school.pk),
        )

        self.assertEqual(confirmed.status_code, status.HTTP_200_OK, confirmed.data)
        self.assertEqual(confirmed.data["status"], SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(FeeLedgerEntry.objects.filter(payment=payment, kind=FeeLedgerEntry.Kind.PAYMENT).count(), 1)
        self.assertEqual(charge_balance_value(charge), 75_000)

    @patch("apps.school_fees.views.provider_for")
    def test_parent_cannot_repeat_a_fee_charge_to_inflate_checkout_amount(self, provider_for_mock):
        self.configure_online()
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider_for_mock.return_value = provider
        before = SchoolFeePayment.objects.count()

        response = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [
                {"fee_charge_id": charge.pk, "amount_minor": 20_000},
                {"fee_charge_id": charge.pk, "amount_minor": 20_000},
            ],
        }, user=self.parent)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(SchoolFeePayment.objects.count(), before)
        provider.initialize.assert_not_called()

    @patch("apps.school_fees.views.provider_for")
    def test_parent_can_pay_for_two_linked_children_in_one_online_checkout(self, provider_for_mock):
        self.configure_online()
        first_charge = self.create_schedule(amount=100_000).charges.get()
        second_student = self.make_student("FEE-005", "Tomi")
        issue_fee_schedule(first_charge.fee_schedule, self.admin)
        second_charge = FeeCharge.objects.get(fee_schedule=first_charge.fee_schedule, student=second_student)
        StudentGuardian.objects.create(
            school=self.school, student=second_student, guardian=self.guardian,
            relationship_type="Parent", can_receive_communications=True,
        )

        linked = self.api("get", "/api/v1/parent/students/", user=self.parent)
        self.assertEqual({row["id"] for row in linked.data}, {self.student.pk, second_student.pk})
        for student in (self.student, second_student):
            fee_list = self.api("get", f"/api/v1/parent/students/{student.pk}/fees/", user=self.parent)
            self.assertEqual(fee_list.status_code, status.HTTP_200_OK, fee_list.data)
            self.assertTrue(fee_list.data["charges"])

        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider.verify.return_value = {
            "reference": "", "status": "success", "amount": 55_000,
            "currency": "NGN", "id": "multi-child-transaction", "channel": "card",
        }
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [
                {"fee_charge_id": first_charge.pk, "amount_minor": 20_000},
                {"fee_charge_id": second_charge.pk, "amount_minor": 35_000},
            ],
        }, user=self.parent)
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        self.assertEqual(initialized.data["amount_minor"], 55_000)
        self.assertIsInstance(initialized.data["amount_minor"], int)
        provider.initialize.assert_called_once()
        self.assertEqual(provider.initialize.call_args.kwargs["amount_minor"], 55_000)
        self.assertIsInstance(provider.initialize.call_args.kwargs["amount_minor"], int)

        payment = SchoolFeePayment.objects.get(reference=initialized.data["reference"])
        provider.verify.return_value["reference"] = payment.reference
        self.assertEqual(payment.amount_minor, 55_000)
        self.assertEqual(payment.provider_metadata["pending_allocations"], [
            {"fee_charge_id": first_charge.pk, "amount_minor": 20_000},
            {"fee_charge_id": second_charge.pk, "amount_minor": 35_000},
        ])
        callback = self.api("post", f"/api/v1/parent/fees/payments/{payment.reference}/", {}, user=self.parent)
        self.assertEqual(callback.status_code, status.HTTP_200_OK, callback.data)
        self.assertEqual(callback.data["status"], SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(FeePaymentAllocation.objects.filter(payment=payment).count(), 2)
        self.assertEqual(FeeLedgerEntry.objects.filter(payment=payment, kind=FeeLedgerEntry.Kind.PAYMENT).count(), 2)
        self.assertEqual(charge_balance_value(first_charge), 80_000)
        self.assertEqual(charge_balance_value(second_charge), 65_000)

    @patch("apps.school_fees.views.provider_for")
    def test_parent_checkout_callback_can_verify_pending_payment_before_allocations_exist(self, provider_for_mock):
        self.configure_online()
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider.verify.return_value = {"reference": "", "status": "success", "amount": 25_000, "currency": "NGN", "id": "123456", "channel": "bank_transfer"}
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 25_000}],
        }, user=self.parent)
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        provider.verify.return_value["reference"] = initialized.data["reference"]
        callback = self.api("post", f"/api/v1/parent/fees/payments/{initialized.data['reference']}/", {}, user=self.parent)
        self.assertEqual(callback.status_code, status.HTTP_200_OK, callback.data)
        self.assertEqual(callback.data["status"], SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(callback.data["method"], SchoolFeePayment.Method.BANK_TRANSFER)
        self.assertEqual(charge_balance_value(charge), 75_000)

    @patch("apps.school_fees.views.provider_for")
    def test_failed_online_callback_does_not_create_fee_ledger_entries(self, provider_for_mock):
        self.configure_online()
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider.verify.return_value = {"reference": "", "status": "failed", "amount": 10_000, "currency": "NGN", "id": "123456"}
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 10_000}],
        }, user=self.parent)
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        provider.verify.return_value["reference"] = initialized.data["reference"]
        callback = self.api("post", f"/api/v1/parent/fees/payments/{initialized.data['reference']}/", {}, user=self.parent)
        self.assertEqual(callback.status_code, status.HTTP_200_OK, callback.data)
        self.assertEqual(callback.data["status"], SchoolFeePayment.Status.FAILED)
        self.assertFalse(FeeLedgerEntry.objects.filter(payment__reference=initialized.data["reference"]).exists())

    @patch("apps.school_fees.views.provider_for")
    def test_verified_success_recovers_online_payment_previously_marked_failed(self, provider_for_mock):
        self.configure_online()
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider.verify.return_value = {"reference": "", "status": "failed", "amount": 10_000, "currency": "NGN", "id": "123456"}
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 10_000}],
        }, user=self.parent)
        reference = initialized.data["reference"]
        provider.verify.return_value["reference"] = reference
        first_check = self.api("post", f"/api/v1/parent/fees/payments/{reference}/", {}, user=self.parent)
        self.assertEqual(first_check.data["status"], SchoolFeePayment.Status.FAILED)
        self.assertFalse(FeeLedgerEntry.objects.filter(payment__reference=reference).exists())

        provider.verify.return_value.update({"status": "success", "amount": 10_000})
        retry = self.api("post", f"/api/v1/parent/fees/payments/{reference}/", {}, user=self.parent)

        self.assertEqual(retry.status_code, status.HTTP_200_OK, retry.data)
        self.assertEqual(retry.data["status"], SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(FeeLedgerEntry.objects.filter(payment__reference=reference, kind=FeeLedgerEntry.Kind.PAYMENT).count(), 1)

    def test_malformed_physical_payment_allocations_return_validation_error(self):
        with self.assertRaises(ValidationError):
            record_physical_payment(
                school=self.school, actor=self.admin, amount_minor=10_000,
                method="cash", allocations=[None],
            )

    @override_settings(PAYSTACK_WEBHOOK_SECRET="school-fee-webhook-secret")
    @patch("apps.school_fees.views.provider_for")
    def test_signed_webhook_verifies_transaction_and_duplicate_event_is_idempotent(self, provider_for_mock):
        charge = self.create_schedule().charges.get()
        payment = SchoolFeePayment.objects.create(
            school=self.school, channel=SchoolFeePayment.Channel.ONLINE, method=SchoolFeePayment.Method.CARD,
            provider="paystack", reference="EDUF-TEST-WEBHOOK", amount_minor=25_000,
            provider_metadata={"pending_allocations": [{"fee_charge_id": charge.pk, "amount_minor": 25_000}]},
        )
        provider = Mock()
        provider.verify.return_value = {"reference": payment.reference, "status": "success", "amount": 25_000, "currency": "NGN", "id": "123456"}
        provider_for_mock.return_value = provider
        payload = json.dumps({"event": "charge.success", "data": {"id": "123456", "reference": payment.reference}}).encode()
        signature = hmac.new(b"school-fee-webhook-secret", payload, hashlib.sha512).hexdigest()
        response = self.client.post("/api/v1/school-fees/webhooks/paystack/", payload, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(payment.ledger_entries.filter(kind=FeeLedgerEntry.Kind.PAYMENT).count(), 1)
        duplicate = self.client.post("/api/v1/school-fees/webhooks/paystack/", payload, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertEqual(PaymentProviderEvent.objects.count(), 1)
        bad = self.client.post("/api/v1/school-fees/webhooks/paystack/", payload, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE="invalid")
        self.assertEqual(bad.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(FLUTTERWAVE_WEBHOOK_SECRET="fee-flw-hook")
    @patch("apps.school_fees.views.provider_for")
    def test_flutterwave_parent_fee_webhook_requeries_provider_and_allocates_once(self, provider_for_mock):
        self.configure_online(provider="flutterwave")
        charge = self.create_schedule().charges.get()
        provider = Mock()
        provider.initialize.return_value = {"authorization_url": "https://checkout.example.test/secure"}
        provider.verify.return_value = {
            "reference": "", "status": "success", "amount": 25_000,
            "currency": "NGN", "id": "654321", "channel": "card",
        }
        provider_for_mock.return_value = provider
        initialized = self.api("post", "/api/v1/parent/fees/payments/initialize/", {
            "allocations": [{"fee_charge_id": charge.pk, "amount_minor": 25_000}],
        }, user=self.parent)
        self.assertEqual(initialized.status_code, status.HTTP_201_CREATED, initialized.data)
        payment = SchoolFeePayment.objects.get(reference=initialized.data["reference"])
        provider.verify.return_value["reference"] = payment.reference
        payload = json.dumps({"event": "charge.completed", "data": {"id": 654321, "tx_ref": payment.reference}}).encode()
        self.client.force_authenticate(user=None)

        first = self.client.post("/api/v1/webhooks/flutterwave/", data=payload, content_type="application/json", HTTP_VERIF_HASH="fee-flw-hook")
        duplicate = self.client.post("/api/v1/webhooks/flutterwave/", data=payload, content_type="application/json", HTTP_VERIF_HASH="fee-flw-hook")
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK, duplicate.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SchoolFeePayment.Status.SUCCESS)
        self.assertEqual(payment.allocations.count(), 1)
        self.assertEqual(payment.ledger_entries.filter(kind=FeeLedgerEntry.Kind.PAYMENT).count(), 1)
        provider.verify.assert_called_once_with(654321)

    def test_termii_failure_does_not_undo_physical_payment_and_receipt_code_is_hashed(self):
        charge = self.create_schedule().charges.get()
        payment = record_physical_payment(school=self.school, actor=self.admin, amount_minor=20_000, method="cash", allocations=[{"fee_charge_id": charge.pk, "amount_minor": 20_000}])
        with patch("apps.school_fees.services._termii_send", side_effect=ImproperlyConfigured("Termii test outage")):
            from .services import notify_payment_guardians, issue_receipt_otp_to_guardians
            notify_payment_guardians(payment.pk)
            with patch("apps.school_fees.services.secrets.randbelow", return_value=123456):
                issue_receipt_otp_to_guardians(payment.pk)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SchoolFeePayment.Status.SUCCESS)
        self.assertTrue(FeeNotification.objects.filter(payment=payment, status=FeeNotification.Status.FAILED).exists())
        challenge = ReceiptOtpChallenge.objects.get(payment=payment)
        self.assertNotEqual(challenge.code_hash, "123456")
        verified = verify_receipt_otp(payment=payment, guardian=self.guardian, code="123456")
        self.assertIsNotNone(verified.verified_at)

    @override_settings(TERMII_API_KEY="test-termii-key", TERMII_SENDER_ID="EDUstacked", TERMII_BASE_URL="https://api.ng.termii.com", TERMII_CHANNEL="generic")
    @patch("apps.school_fees.services.urlopen")
    def test_termii_accepts_current_success_response_and_normalizes_nigerian_phone(self, urlopen_mock):
        from .services import _termii_send
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"message_id": "termii-123", "message": "Successfully Sent"}).encode()
        urlopen_mock.return_value = response
        self.assertEqual(_termii_send("+234 803 123 4567", "Test SMS"), "termii-123")
        payload = json.loads(urlopen_mock.call_args.args[0].data.decode())
        self.assertEqual(payload["to"], "2348031234567")
        self.assertEqual(urlopen_mock.call_args.args[0].full_url, "https://api.ng.termii.com/api/sms/send")

    @patch.object(FlutterwaveSchoolProvider, "_request")
    def test_flutterwave_routes_the_full_school_fee_to_its_verified_subaccount(self, request_mock):
        request_mock.side_effect = [
            {"account_name": "NORTHSIDE ACADEMY"},
            {"subaccount_id": "RS_SCHOOL_1"},
            {"link": "https://checkout.example.test/fee"},
        ]
        provider = FlutterwaveSchoolProvider()
        connected = provider.connect_account(
            bank_code="044", account_number="0123456789", business_name="Northside Academy",
            phone="08030000000", business_email="office@northside.example",
        )
        payload = request_mock.call_args_list[1].args[2]
        self.assertEqual(payload["split_type"], "percentage")
        self.assertEqual(payload["split_value"], 0.0)
        self.assertEqual(payload["business_email"], "office@northside.example")
        self.assertEqual(connected["provider_account_id"], "RS_SCHOOL_1")
        provider.initialize(
            email="parent@example.test", amount_minor=100_000, reference="EDUF-TEST-1",
            callback_url="https://school.example.test/parent", subaccount_id=connected["provider_account_id"],
            channels=["card", "bank_transfer", "ussd"],
        )
        checkout_payload = request_mock.call_args_list[2].args[2]
        self.assertEqual(checkout_payload["payment_options"], "card, banktransfer, ussd")

    def test_receipt_pdf_contains_a_school_fee_receipt(self):
        charge = self.create_schedule().charges.get()
        payment = self.record_manual(charge, 20_000)
        response = self.api("get", f"/api/v1/school-fees/payments/{payment.data['reference']}/receipt/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_reversal_restores_balance_and_records_an_auditable_refund(self):
        charge = self.create_schedule().charges.get()
        payment = self.record_manual(charge, 40_000)
        reference = payment.data["reference"]
        response = self.api("post", f"/api/v1/school-fees/payments/{reference}/reverse/", {"amount_minor": 15_000, "reason": "Incorrect amount entered"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], SchoolFeePayment.Status.PARTIALLY_REVERSED)
        self.assertEqual(charge_balance_value(charge), 75_000)
        self.assertEqual(FeeLedgerEntry.objects.filter(payment__reference=reference, kind=FeeLedgerEntry.Kind.REFUND).aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount_minor"))["total"], 15_000)


def charge_balance_value(charge):
    return max(0, int(charge.ledger_entries.aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount_minor"))["total"] or 0))
