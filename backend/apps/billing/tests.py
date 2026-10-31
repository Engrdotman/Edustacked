import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework import status

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.report_cards.models import ReportCard, ReportCardRevision
from apps.results.models import AssessmentPlan, AssessmentResult
from apps.schools.models import School
from apps.students.models import Student, StudentEnrollment
from apps.billing.models import CreditAccount, CreditPackage, CreditPayment, CreditTransaction, ReportCardBilling
from apps.billing.serializers import CreditPackageSerializer
from apps.report_cards.tests import ReportCardApiTests


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",), PAYSTACK_SECRET_KEY="sk_test_unit-test", FRONTEND_BASE_URL="https://school.example.test", DEBUG=True)
class BillingIntegrationTests(ReportCardApiTests):
    def prepare_approved_card(self):
        card = self.generate()
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{card['id']}/approve/", {}).status_code, status.HTTP_200_OK)
        return card

    def test_three_default_credit_packages_use_the_configured_volume_rates(self):
        response = self.api("get", "/api/v1/billing/packages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        packages = {package["credits"]: package for package in response.data}
        self.assertEqual(set(packages), {100, 300, 500})
        expected = {100: (3_000_000, "300.00"), 300: (4_500_000, "150.00"), 500: (5_000_000, "100.00")}
        for credits, (total_minor, rate) in expected.items():
            self.assertEqual(packages[credits]["price_minor"], total_minor)
            self.assertEqual(packages[credits]["price_per_credit_naira"], rate)

    def test_first_finalization_charges_once_and_reprint_does_not(self):
        account = CreditAccount.objects.get(school=self.school)
        account.balance = 2
        account.save(update_fields=("balance",))
        card = self.prepare_approved_card()
        response = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["billing"], {"credit_charged": True, "credit_balance": 1})
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 1)
        self.assertEqual(ReportCardBilling.objects.filter(school=self.school, student=self.student, academic_session=self.session, term=self.term).count(), 1)
        # A correction revision belongs to the same billable term and stays free.
        self.result.approved_total = "90"
        self.result.approved_percentage = "90"
        self.result.approved_calculation = {**self.result.approved_calculation, "calculated_total": "90", "percentage": "90"}
        self.result.save()
        correction = self.api("post", f"/api/v1/report-cards/{card['id']}/correct/", {"reason": "Corrected source"})
        self.assertEqual(correction.status_code, status.HTTP_200_OK)
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{card['id']}/approve/", {}).status_code, status.HTTP_200_OK)
        revised = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(revised.status_code, status.HTTP_200_OK, revised.data)
        self.assertFalse(revised.data["billing"]["credit_charged"])
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 1)
        self.assertEqual(CreditTransaction.objects.filter(school=self.school, kind=CreditTransaction.Kind.REPORT_CARD).count(), 1)

    def test_insufficient_credit_blocks_finalization_without_blocking_preview(self):
        CreditAccount.objects.filter(school=self.school).update(balance=0)
        card = self.prepare_approved_card()
        preview = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/?preview=true")
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        denied = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("credits", denied.data)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 0)
        self.assertFalse(ReportCardBilling.objects.filter(school=self.school, student=self.student, academic_session=self.session, term=self.term).exists())

    def test_download_retry_and_duplicate_finalize_do_not_charge(self):
        CreditAccount.objects.filter(school=self.school).update(balance=1)
        card = self.prepare_approved_card()
        first = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        balance = CreditAccount.objects.get(school=self.school).balance
        pdf = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        retry = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(retry.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, balance)
        self.assertEqual(CreditTransaction.objects.filter(school=self.school, kind=CreditTransaction.Kind.REPORT_CARD).count(), 1)

    def test_new_term_is_a_distinct_billable_period(self):
        CreditAccount.objects.filter(school=self.school).update(balance=2)
        first = self.prepare_approved_card()
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{first['id']}/finalize/", {}).status_code, status.HTTP_200_OK)
        second_term = Term.objects.create(school=self.school, academic_session=self.session, name="Second Term", sequence=2, start_date=date(2027, 1, 10), end_date=date(2027, 4, 10))
        plan = AssessmentPlan.objects.create(
            school=self.school, academic_session=self.session, term=second_term,
            class_level=self.level, class_arm=self.arm, subject=self.subject,
            grading_scale=self.scale, name="Second Term Assessment",
            grading_scale_snapshot=self.scale_snapshot, status=AssessmentPlan.Status.PUBLISHED,
            created_by=self.admin,
        )
        result = AssessmentResult.objects.create(
            school=self.school, plan=plan, student=self.student, enrollment=self.enrollment,
            status=AssessmentResult.Status.APPROVED, approved_total="80", approved_maximum="100",
            approved_percentage="80", approved_grade="A", approved_grade_point="4",
            approved_calculation={"complete": True, "components": [{"name": "Exam", "score": "80", "max_score": "100"}]},
        )
        generated = self.api("post", "/api/v1/report-cards/generate/", {"enrollment": self.enrollment.pk, "term": second_term.pk})
        self.assertEqual(generated.status_code, status.HTTP_201_CREATED, generated.data)
        second_id = generated.data["report_card"]["id"]
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{second_id}/review/", {}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.api("post", f"/api/v1/report-cards/{second_id}/approve/", {}).status_code, status.HTTP_200_OK)
        finalized = self.api("post", f"/api/v1/report-cards/{second_id}/finalize/", {})
        self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
        self.assertTrue(finalized.data["billing"]["credit_charged"])
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 0)
        self.assertEqual(ReportCardBilling.objects.filter(school=self.school, student=self.student).count(), 2)

    @patch("apps.billing.providers.PaystackProvider.initialize", return_value={"authorization_url": "https://checkout.paystack.com/test"})
    def test_failed_provider_status_and_cross_school_payment_lookup(self, _initialize):
        package = CreditPackage.objects.create(name="Failure pack", credits=3, price_minor=30000)
        started = self.api("post", "/api/v1/billing/purchases/", {"package": package.pk})
        payment = CreditPayment.objects.get(reference=started.data["reference"])
        self.client.force_authenticate(self.other_admin)
        hidden = self.api("get", f"/api/v1/billing/payments/{payment.reference}/", school=self.other_school)
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.admin)
        with patch("apps.billing.views.PaystackProvider.verify", return_value={"reference": payment.reference, "status": "failed"}):
            failed = self.api("post", f"/api/v1/billing/payments/{payment.reference}/", {})
        self.assertEqual(failed.status_code, status.HTTP_200_OK)
        self.assertEqual(failed.data["status"], CreditPayment.Status.FAILED)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 20)
        self.assertFalse(CreditTransaction.objects.filter(payment=payment).exists())

    @patch("apps.billing.providers.PaystackProvider.initialize", return_value={"authorization_url": "https://checkout.paystack.com/test", "access_code": "test-access"})
    def test_package_price_is_server_controlled_and_verified_purchase_idempotent(self, _initialize):
        package = CreditPackage.objects.create(name="Starter", credits=5, price_minor=125000, is_active=True)
        package_details = CreditPackageSerializer(package).data
        self.assertEqual(package_details["price_naira"], "1,250.00")
        self.assertEqual(package_details["price_per_credit_naira"], "250.00")
        started = self.api("post", "/api/v1/billing/purchases/", {"package": package.pk, "amount": 1, "credits": 999})
        self.assertEqual(started.status_code, status.HTTP_201_CREATED, started.data)
        self.assertEqual(started.data["amount_minor"], 125000)
        self.assertEqual(started.data["credits"], 5)
        payment = CreditPayment.objects.get(reference=started.data["reference"])
        pending_status = self.api("get", f"/api/v1/billing/payments/{payment.reference}/")
        self.assertEqual(pending_status.status_code, status.HTTP_200_OK)
        self.assertEqual(pending_status.data["status"], CreditPayment.Status.PENDING)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 20)
        verified = {"id": 12345, "reference": payment.reference, "status": "success", "amount": 125000, "currency": "NGN", "customer": {"email": payment.customer_email}}
        with patch("apps.billing.views.PaystackProvider.verify", return_value=verified) as verify:
            result = self.api("post", f"/api/v1/billing/payments/{payment.reference}/", {})
            self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)
            self.assertEqual(result.data["status"], CreditPayment.Status.SUCCESS)
            self.assertEqual(result.data["balance"], 25)
            again = self.api("post", f"/api/v1/billing/payments/{payment.reference}/", {})
            self.assertEqual(again.status_code, status.HTTP_200_OK)
            self.assertEqual(again.data["balance"], 25)
            verify.assert_called_once()
        self.assertEqual(CreditTransaction.objects.filter(payment=payment, kind=CreditTransaction.Kind.PURCHASE).count(), 1)

    @patch("apps.billing.providers.PaystackProvider.initialize", return_value={"authorization_url": "https://checkout.paystack.com/test"})
    def test_signed_duplicate_webhooks_grant_once_and_invalid_signature_grants_nothing(self, _initialize):
        package = CreditPackage.objects.create(name="Webhook pack", credits=3, price_minor=30000)
        started = self.api("post", "/api/v1/billing/purchases/", {"package": package.pk})
        payment = CreditPayment.objects.get(reference=started.data["reference"])
        event = {"event": "charge.success", "data": {"id": 321, "reference": payment.reference, "status": "success", "amount": payment.amount_minor, "currency": "NGN", "customer": {"email": payment.customer_email}}}
        raw = json.dumps(event, separators=(",", ":")).encode()
        signature = hmac.new(b"sk_test_unit-test", raw, hashlib.sha512).hexdigest()
        self.client.force_authenticate(user=None)
        path = "/api/v1/billing/paystack/webhook/"
        bad = self.client.post(path, data=raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE="invalid")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 20)
        for _ in range(2):
            response = self.client.post(path, data=raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 23)
        self.assertEqual(CreditTransaction.objects.filter(payment=payment).count(), 1)

    @patch("apps.billing.providers.PaystackProvider.initialize", return_value={"authorization_url": "https://checkout.paystack.com/test"})
    def test_processed_refund_is_audited_without_automatic_negative_balance(self, _initialize):
        package = CreditPackage.objects.create(name="Refund pack", credits=2, price_minor=20000)
        started = self.api("post", "/api/v1/billing/purchases/", {"package": package.pk})
        payment = CreditPayment.objects.get(reference=started.data["reference"])
        success = {"id": 789, "reference": payment.reference, "status": "success", "amount": payment.amount_minor, "currency": "NGN", "customer": {"email": payment.customer_email}}
        with patch("apps.billing.views.PaystackProvider.verify", return_value=success):
            paid = self.api("post", f"/api/v1/billing/payments/{payment.reference}/", {})
        self.assertEqual(paid.data["status"], CreditPayment.Status.SUCCESS)
        data = {"transaction_reference": payment.reference, "status": "processed", "amount": "20000", "currency": "NGN"}
        event = {"event": "refund.processed", "data": data}
        raw = json.dumps(event, separators=(",", ":")).encode()
        signature = hmac.new(b"sk_test_unit-test", raw, hashlib.sha512).hexdigest()
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/v1/billing/paystack/webhook/", data=raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, CreditPayment.Status.REVERSED)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 22)
        self.assertTrue(payment.reconciliation_issues.filter(kind="payment_reversal").exists())

    def test_tenant_and_role_scoping_and_platform_adjustment_audit(self):
        self.client.force_authenticate(self.teacher_user)
        denied = self.api("get", "/api/v1/billing/credits/")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_admin)
        hidden = self.api("get", "/api/v1/billing/credits/", school=self.other_school)
        self.assertEqual(hidden.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden.data["balance"], 0)
        self.client.force_authenticate(user=None)
        platform_user = self.make_user("platform-billing", "school_admin", self.school)
        platform_user.is_superuser = True
        platform_user.save(update_fields=("is_superuser",))
        self.client.force_authenticate(platform_user)
        adjusted = self.client.post("/api/v1/platform/billing/adjustments/", {"school": self.school.pk, "amount": 2, "reason": "Approved launch grant", "reference_key": "grant:launch:one"}, format="json")
        self.assertEqual(adjusted.status_code, status.HTTP_201_CREATED, adjusted.data)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 22)
        duplicate = self.client.post("/api/v1/platform/billing/adjustments/", {"school": self.school.pk, "amount": 2, "reason": "Duplicate", "reference_key": "grant:launch:one"}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)


@skipUnlessDBFeature("has_select_for_update")
class BillingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Concurrency School", slug="concurrency-school")
        self.user = User.objects.create_user(username="concurrent-admin", email="concurrent@example.test", password="test-password")
        session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        term = Term.objects.create(school=self.school, academic_session=session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        arm = ClassArm.objects.create(school=self.school, class_level=level, name="A")
        student = Student.objects.create(school=self.school, admission_number="CON-1", first_name="Test", last_name="Student")
        enrollment = StudentEnrollment.objects.create(school=self.school, student=student, academic_session=session, class_level=level, class_arm=arm, enrollment_date=date(2026, 9, 1))
        self.card = ReportCard.objects.create(school=self.school, student=student, enrollment=enrollment, academic_session=session, term=term, class_level=level, class_arm=arm, identifier="RC-CONCURRENT", created_by=self.user, status=ReportCard.Status.APPROVED)
        self.revision = ReportCardRevision.objects.create(report_card=self.card, revision_number=1, status=ReportCardRevision.Status.APPROVED, generated_by=self.user)
        CreditAccount.objects.create(school=self.school, balance=1)

    def test_parallel_finalization_spends_one_credit(self):
        from threading import Barrier
        barrier = Barrier(2)

        def finalize():
            from apps.billing.services import finalize_report_card_with_credit
            from django.core.exceptions import ValidationError
            from django.db import close_old_connections
            close_old_connections()
            barrier.wait()
            try:
                card = ReportCard.objects.get(pk=self.card.pk)
                with patch("apps.billing.services.validate_revision_ready"):
                    finalize_report_card_with_credit(card, self.user)
                return "finalized"
            except ValidationError:
                return "already-finalized"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: finalize(), range(2)))
        self.assertEqual(outcomes.count("finalized"), 1)
        self.assertEqual(CreditAccount.objects.get(school=self.school).balance, 0)
        self.assertEqual(CreditTransaction.objects.filter(kind=CreditTransaction.Kind.REPORT_CARD).count(), 1)
