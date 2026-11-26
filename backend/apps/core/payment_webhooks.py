"""Shared public webhook endpoints for payment providers."""
import json

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.services import flutterwave_signature_is_valid


class FlutterwaveWebhookView(APIView):
    """Route a Flutterwave charge notification to its matching product flow."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, **kwargs):
        if not flutterwave_signature_is_valid(request.headers.get("verif-hash", "")):
            return Response({"detail": "Webhook signature could not be verified."}, status=401)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (AttributeError, TypeError, ValueError, UnicodeDecodeError):
            return Response({"detail": "Invalid webhook payload."}, status=400)
        if not isinstance(payload, dict):
            return Response({"detail": "Invalid webhook payload."}, status=400)

        data = payload.get("data")
        if not isinstance(data, dict):
            return Response({"detail": "Payment event is missing transaction details."}, status=400)
        event_type = str(payload.get("event") or "")
        if event_type.lower().startswith("refund."):
            refund_status = str(data.get("status") or "").lower()
            if refund_status not in {
                "completed", "completed-bank-transfer", "completed-momo",
                "completed-mpgs", "completed-offline", "completed-preauth", "succeeded",
            }:
                return Response({"received": True})
            transaction_id = str(data.get("tx_id") or data.get("charge_id") or "").strip()
            if not transaction_id:
                return Response({"received": True})

            # Do not claw back a school's value based on a refund notification.
            # Record a platform reconciliation item so an operator can verify
            # the provider refund and reverse the correct product ledger safely.
            from apps.billing.models import CreditPayment, ReconciliationIssue
            payment = CreditPayment.objects.filter(
                provider="flutterwave", provider_transaction_id=transaction_id,
            ).select_related("school").first()
            school = payment.school if payment else None
            if school is None:
                from apps.school_fees.models import SchoolFeePayment
                fee_payment = SchoolFeePayment.objects.filter(
                    provider="flutterwave", provider_transaction_id=transaction_id,
                    channel=SchoolFeePayment.Channel.ONLINE,
                ).select_related("school").first()
                school = fee_payment.school if fee_payment else None
            if school is None:
                from apps.sms_management.models import SMSPurchase
                sms_payment = SMSPurchase.objects.filter(
                    provider="flutterwave", provider_transaction_id=transaction_id,
                ).select_related("school").first()
                school = sms_payment.school if sms_payment else None
            if school is None:
                return Response({"received": True})

            refund_reference = str(data.get("id") or data.get("flw_ref") or transaction_id)[:90]
            amount = data.get("amount_refunded", data.get("amount", "unknown"))
            ReconciliationIssue.objects.get_or_create(
                kind="provider_refund",
                provider_reference=f"flutterwave-refund:{refund_reference}"[:100],
                defaults={
                    "school": school,
                    "payment": payment,
                    "description": (
                        f"Flutterwave reported a refund ({refund_status}, amount {amount}). "
                        "Verify the refund in Flutterwave and reconcile the affected product ledger."
                    )[:500],
                },
            )
            return Response({"received": True, "reconciliation_required": True})

        # Acknowledge signed events unrelated to charges. Flutterwave only needs
        # a 200 response when an event is safely ignored.
        if event_type != "charge.completed":
            return Response({"received": True})
        reference = str(data.get("tx_ref") or "").strip()
        if not reference:
            return Response({"detail": "Payment event is missing its transaction reference."}, status=400)

        # Import product views lazily to avoid app-loading import cycles. Their
        # handlers recheck the signature, verify the transaction with Flutterwave,
        # and apply idempotent ledger updates before acknowledging the event.
        from apps.billing.models import CreditPayment
        if CreditPayment.objects.filter(provider="flutterwave", reference=reference).exists():
            from apps.billing.views import FlutterwaveWebhookView as CreditWebhookView
            return CreditWebhookView().post(request)

        from apps.school_fees.models import SchoolFeePayment
        if SchoolFeePayment.objects.filter(
            provider="flutterwave", reference=reference,
            channel=SchoolFeePayment.Channel.ONLINE,
        ).exists():
            from apps.school_fees.views import PaymentWebhookView
            return PaymentWebhookView().post(request, provider_name="flutterwave")

        from apps.sms_management.models import SMSPurchase
        if SMSPurchase.objects.filter(provider="flutterwave", reference=reference).exists():
            from apps.sms_management.views import SMSPaymentWebhookView
            return SMSPaymentWebhookView().post(request, provider_name="flutterwave")

        # Unknown but correctly signed references are not orders managed here.
        return Response({"received": True})
