import hashlib
import hmac
import json
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.schools.models import School, SchoolMembership

from .models import SMSBundle, SMSMessageLog, SMSMonthlyAllowance, SMSPurchase, SMSWallet, SMSWalletTransaction
from .services import apply_sms_purchase_result, ensure_monthly_allowance, initialize_sms_purchase, issue_monthly_allowances, sms_segments

User = get_user_model()


@override_settings(TERMII_API_KEY="test-token", TERMII_SENDER_ID="EDUstacked", FRONTEND_BASE_URL="https://edustacked.example")
class SMSManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username="sms-owner", email="sms-owner@example.test", password="Safe-test-password-1")
        self.school = School.objects.create(name="SMS Test School")
        SchoolMembership.objects.create(user=self.owner, school=self.school, role=SchoolMembership.Role.SCHOOL_OWNER)
        self.client.force_authenticate(self.owner)
        self.client.defaults["HTTP_X_SCHOOL_ID"] = str(self.school.pk)
        self.bundle = SMSBundle.objects.create(name="Basic Test", credits=500, price_minor=375000)
        self.allowance = ensure_monthly_allowance(self.school)

    def send(self, phones, message="A school update", key="sms-test-1"):
        return self.client.post(
            reverse("sms-send", kwargs={"version": "v1"}),
            {"recipients": phones, "message": message}, format="json",
            HTTP_X_SCHOOL_ID=str(self.school.pk), HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_segment_count_uses_gsm_and_unicode_limits(self):
        self.assertEqual(sms_segments("a" * 160), 1)
        self.assertEqual(sms_segments("a" * 161), 2)
        self.assertEqual(sms_segments("🙂" * 70), 1)
        self.assertEqual(sms_segments("🙂" * 71), 2)

    def test_monthly_allowance_is_created_once_for_calendar_period(self):
        repeated = ensure_monthly_allowance(self.school)
        self.assertEqual(repeated.pk, self.allowance.pk)
        before = SMSMonthlyAllowance.objects.filter(school=self.school, month_start=self.allowance.month_start).count()
        result = issue_monthly_allowances()
        after = SMSMonthlyAllowance.objects.filter(school=self.school, month_start=self.allowance.month_start).count()
        self.assertEqual(before, 1)
        self.assertEqual(after, 1)
        self.assertEqual(result["created"], 0)

    def test_new_calendar_month_gets_a_separate_non_rollover_allowance(self):
        self.allowance.used_credits = 40
        self.allowance.save(update_fields=("used_credits", "updated_at"))

        next_month = ensure_monthly_allowance(self.school, on_date=date(2027, 1, 12))

        self.assertEqual(next_month.month_start, date(2027, 1, 1))
        self.assertEqual(next_month.allowance_credits, 50)
        self.assertEqual(next_month.used_credits, 0)

    @patch("apps.sms_management.services.termii_send_raw", side_effect=("termii-message-1", "termii-message-2"))
    def test_free_sms_are_used_before_paid_wallet_and_retries_do_not_send_twice(self, send_raw):
        self.allowance.used_credits = 49
        self.allowance.save(update_fields=("used_credits", "updated_at"))
        wallet = SMSWallet.objects.create(school=self.school, purchased_balance=20, paid_value_balance_minor=15000)

        first = self.send(["08031234567"], key="request-a")
        repeated = self.send(["08031234567"], key="request-a")
        second = self.send(["08031234568"], key="request-b")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["free_credits"], 1)
        self.assertEqual(first.data["paid_credits"], 0)
        self.assertTrue(repeated.data["replayed"])
        self.assertEqual(second.data["free_credits"], 0)
        self.assertEqual(second.data["paid_credits"], 1)
        self.assertEqual(send_raw.call_count, 2)
        wallet.refresh_from_db()
        self.assertEqual(wallet.purchased_balance, 19)
        self.assertEqual(self.allowance.__class__.objects.get(pk=self.allowance.pk).used_credits, 50)
        self.assertEqual(SMSWalletTransaction.objects.filter(kind=SMSWalletTransaction.Kind.CONSUMPTION).count(), 1)

    @patch("apps.sms_management.services.termii_send_raw")
    def test_insufficient_free_and_paid_balance_blocks_without_provider_send(self, send_raw):
        self.allowance.used_credits = self.allowance.allowance_credits
        self.allowance.save(update_fields=("used_credits", "updated_at"))
        response = self.send(["08031234567"], key="no-balance")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Not enough SMS credits", str(response.data))
        send_raw.assert_not_called()
        self.assertFalse(SMSMessageLog.objects.exists())

    @patch("apps.sms_management.services.termii_send_raw")
    def test_unicode_multisegment_message_debits_all_segments(self, send_raw):
        self.allowance.used_credits = self.allowance.allowance_credits
        self.allowance.save(update_fields=("used_credits", "updated_at"))
        wallet = SMSWallet.objects.create(school=self.school, purchased_balance=4, paid_value_balance_minor=30000)
        send_raw.return_value = "termii-unicode-1"

        response = self.send(["08031234567"], message="🙂" * 71, key="unicode")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["total_segments"], 2)
        self.assertEqual(response.data["paid_credits"], 2)
        wallet.refresh_from_db()
        self.assertEqual(wallet.purchased_balance, 2)

    @patch("apps.sms_management.services.termii_send_raw", side_effect=Exception("network timeout"))
    def test_ambiguous_provider_result_is_held_without_refund(self, send_raw):
        response = self.send(["08031234567"], key="ambiguous")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["messages"][0]["status"], "unknown")
        self.assertEqual(self.allowance.__class__.objects.get(pk=self.allowance.pk).used_credits, 1)

    @patch("apps.sms_management.services.termii_send_raw")
    def test_explicit_provider_rejection_refunds_free_allowance(self, send_raw):
        from .services import TermiiRejected
        send_raw.side_effect = TermiiRejected("number rejected")
        response = self.send(["08031234567"], key="rejected")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["messages"][0]["status"], "failed")
        self.assertEqual(self.allowance.__class__.objects.get(pk=self.allowance.pk).used_credits, 0)

    def test_payment_confirmation_credits_wallet_once(self):
        payment = SMSPurchase.objects.create(
            school=self.school, bundle=self.bundle, bundle_name=self.bundle.name,
            credits=self.bundle.credits, amount_minor=self.bundle.price_minor,
            provider=SMSPurchase.Provider.PAYSTACK, reference="SMS-UNIQUE-REF",
            customer_email=self.owner.email, created_by=self.owner,
        )
        provider_result = {"reference": payment.reference, "status": "success", "amount": payment.amount_minor, "currency": "NGN", "id": "provider-42"}

        apply_sms_purchase_result(payment, provider_result)
        apply_sms_purchase_result(payment, provider_result)

        wallet = SMSWallet.objects.get(school=self.school)
        self.assertEqual(wallet.purchased_balance, 500)
        self.assertEqual(wallet.paid_value_balance_minor, 375000)
        self.assertEqual(SMSWalletTransaction.objects.filter(kind=SMSWalletTransaction.Kind.PURCHASE).count(), 1)

    @patch("apps.sms_management.services.PaystackProvider")
    def test_purchase_checkout_uses_existing_paystack_provider_and_keeps_wallet_pending(self, provider_class):
        provider_class.return_value.initialize.return_value = {"authorization_url": "https://checkout.paystack.com/sms-test"}

        purchase = initialize_sms_purchase(school=self.school, user=self.owner, bundle=self.bundle, provider_name="paystack")

        provider_class.return_value.initialize.assert_called_once()
        self.assertEqual(purchase.status, SMSPurchase.Status.PENDING)
        self.assertEqual(purchase.authorization_url, "https://checkout.paystack.com/sms-test")
        self.assertFalse(SMSWallet.objects.filter(school=self.school).exists())

    def test_payment_amount_mismatch_never_credits_wallet(self):
        from django.core.exceptions import ValidationError
        payment = SMSPurchase.objects.create(
            school=self.school, bundle=self.bundle, bundle_name=self.bundle.name,
            credits=self.bundle.credits, amount_minor=self.bundle.price_minor,
            provider=SMSPurchase.Provider.PAYSTACK, reference="SMS-BAD-AMOUNT",
            customer_email=self.owner.email, created_by=self.owner,
        )

        with self.assertRaises(ValidationError):
            apply_sms_purchase_result(payment, {"reference": payment.reference, "status": "success", "amount": 1, "currency": "NGN"})

        self.assertFalse(SMSWallet.objects.filter(school=self.school).exists())

    @override_settings(TERMII_WEBHOOK_SECRET="termii-hook-secret")
    @patch("apps.sms_management.services.termii_send_raw", return_value="termii-refund-test")
    def test_signed_termii_failed_delivery_refunds_paid_credit_and_duplicate_callback_is_safe(self, send_raw):
        from apps.sms_management.models import SMSMessageLog
        self.allowance.used_credits = self.allowance.allowance_credits
        self.allowance.save(update_fields=("used_credits", "updated_at"))
        SMSWallet.objects.create(school=self.school, purchased_balance=1, paid_value_balance_minor=750)
        sent = self.send(["08031234567"], key="termii-refund")
        self.assertEqual(sent.status_code, 201, sent.data)
        message = SMSMessageLog.objects.get(provider_message_id="termii-refund-test")
        payload = {"message_id": message.provider_message_id, "status": "Message Failed", "cost": 6}
        body = json.dumps(payload).encode()
        signature = hmac.new(b"termii-hook-secret", body, hashlib.sha512).hexdigest()
        endpoint = reverse("sms-termii-webhook", kwargs={"version": "v1"})

        first = self.client.generic("POST", endpoint, body, content_type="application/json", HTTP_X_TERMII_SIGNATURE=signature)
        repeated = self.client.generic("POST", endpoint, body, content_type="application/json", HTTP_X_TERMII_SIGNATURE=signature)

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(SMSWallet.objects.get(school=self.school).purchased_balance, 1)
        self.assertEqual(SMSWalletTransaction.objects.filter(kind=SMSWalletTransaction.Kind.REFUND).count(), 1)
        message.refresh_from_db()
        self.assertEqual(message.status, SMSMessageLog.Status.FAILED)

    @override_settings(PAYSTACK_WEBHOOK_SECRET="sms-hook-secret")
    @patch("apps.sms_management.views.PaystackWebhookVerify.verify")
    def test_payment_webhook_signature_and_duplicate_event_are_idempotent(self, verify):
        payment = SMSPurchase.objects.create(
            school=self.school, bundle=self.bundle, bundle_name=self.bundle.name,
            credits=self.bundle.credits, amount_minor=self.bundle.price_minor,
            provider=SMSPurchase.Provider.PAYSTACK, reference="SMS-WEBHOOK-REF",
            customer_email=self.owner.email, created_by=self.owner,
        )
        verify.return_value = {"reference": payment.reference, "status": "success", "amount": payment.amount_minor, "currency": "NGN", "id": "provider-43"}
        body = json.dumps({"event": "charge.success", "data": {"id": "ev-1", "reference": payment.reference}}).encode()
        signature = hmac.new(b"sms-hook-secret", body, hashlib.sha512).hexdigest()
        endpoint = reverse("sms-payment-webhook", kwargs={"version": "v1", "provider_name": "paystack"})

        first = self.client.generic("POST", endpoint, body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        repeated = self.client.generic("POST", endpoint, body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertTrue(repeated.data["duplicate"])
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(SMSWallet.objects.get(school=self.school).purchased_balance, 500)

    def test_school_users_cannot_read_platform_sms_analytics_or_other_wallet(self):
        other_school = School.objects.create(name="Other SMS School")
        own_school = self.client.get(reverse("sms-overview", kwargs={"version": "v1"}), HTTP_X_SCHOOL_ID=str(self.school.pk))
        cross_school = self.client.get(reverse("sms-overview", kwargs={"version": "v1"}), HTTP_X_SCHOOL_ID=str(other_school.pk))
        platform = self.client.get(reverse("platform-sms-overview", kwargs={"version": "v1"}))
        self.assertEqual(own_school.status_code, 200)
        self.assertEqual(cross_school.status_code, 403)
        self.assertEqual(platform.status_code, 403)

    def test_platform_superuser_can_view_analytics_and_manage_bundle_pricing(self):
        platform_owner = User.objects.create_superuser(username="sms-platform", email="platform-sms@example.test", password="Safe-test-password-2")
        self.client.force_authenticate(platform_owner)
        overview = self.client.get(reverse("platform-sms-overview", kwargs={"version": "v1"}))
        update = self.client.patch(
            reverse("platform-sms-bundle-detail", kwargs={"version": "v1", "pk": self.bundle.pk}),
            {"price_minor": 400000}, format="json",
        )

        self.assertEqual(overview.status_code, 200, overview.data)
        self.assertEqual(overview.data["overview"]["schools_count"], 1)
        self.assertEqual(update.status_code, 200, update.data)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.price_minor, 400000)

    def test_monthly_issue_command_can_be_run_more_than_once(self):
        call_command("issue_sms_monthly_allowances")
        call_command("issue_sms_monthly_allowances")
        self.assertEqual(SMSMonthlyAllowance.objects.filter(school=self.school, month_start=date.today().replace(day=1)).count(), 1)
