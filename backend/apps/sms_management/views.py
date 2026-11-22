import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.billing.providers import FlutterwaveProvider
from apps.schools.models import School
from apps.schools.permissions import HasSchoolPermission, IsPlatformSuperadmin
from apps.schools.tenancy import resolve_authorized_school

from .models import (
    SMSBundle, SMSMessageBatch, SMSMessageLog, SMSMonthlyAllowance,
    SMSPlatformConfiguration, SMSProviderEvent, SMSPurchase, SMSWallet,
    SMSWalletTransaction,
)
from .serializers import (
    SMSBatchSerializer, SMSBundleManageSerializer, SMSBundleSerializer,
    SMSDateRangeSerializer, SMSMessageLogSerializer, SMSPlatformConfigurationSerializer,
    SMSPurchaseInitSerializer, SMSPurchaseSerializer, SMSSendSerializer,
    SMSWalletTransactionSerializer,
)
from .services import (
    apply_delivery_report, apply_sms_purchase_result, ensure_monthly_allowance,
    initialize_sms_purchase, issue_monthly_allowances, platform_config,
    send_school_sms, termii_signature_is_valid, verify_sms_purchase,
)


def _school(request):
    return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))


def _can_view_financial_history(user, school, request):
    if user.is_superuser:
        return True
    from apps.schools.permissions import authorized_membership
    from apps.schools.models import SchoolMembership
    view = type("RequestView", (), {"kwargs": {}})()
    return authorized_membership(user, request, view).role in {
        SchoolMembership.Role.SCHOOL_OWNER, SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.PRINCIPAL,
    }


class SMSOverviewView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "sms.view"

    def get(self, request, **kwargs):
        school = _school(request)
        month = ensure_monthly_allowance(school)
        wallet, _ = SMSWallet.objects.get_or_create(school=school)
        messages = SMSMessageLog.objects.filter(school=school)
        next_month = date(month.month_start.year + (month.month_start.month == 12), month.month_start.month % 12 + 1, 1)
        month_messages = messages.filter(created_at__date__gte=month.month_start, created_at__date__lt=next_month)
        data = {
            "school_name": school.name,
            "configured": bool(settings.TERMII_API_KEY and settings.TERMII_SENDER_ID),
            "monthly_allowance": {
                "month_start": month.month_start,
                "allowance_credits": month.allowance_credits,
                "used_credits": month.used_credits,
                "remaining_credits": max(0, month.allowance_credits - month.used_credits),
            },
            "wallet": {
                "purchased_balance": wallet.purchased_balance,
                "sending_suspended": wallet.sending_suspended,
                "suspension_reason": wallet.suspension_reason,
                "low_balance_threshold": platform_config().low_balance_threshold,
            },
            "monthly_usage": {
                "messages": month_messages.count(),
                "segments": month_messages.filter(status__in=(SMSMessageLog.Status.SUBMITTED, SMSMessageLog.Status.DELIVERED, SMSMessageLog.Status.UNKNOWN)).aggregate(total=Sum("segments"))["total"] or 0,
                "delivered": month_messages.filter(status=SMSMessageLog.Status.DELIVERED).count(),
                "failed": month_messages.filter(status=SMSMessageLog.Status.FAILED).count(),
                "paid_credits": month_messages.filter(status__in=(SMSMessageLog.Status.SUBMITTED, SMSMessageLog.Status.DELIVERED, SMSMessageLog.Status.UNKNOWN)).aggregate(total=Sum("paid_credits"))["total"] or 0,
                "free_credits": month_messages.filter(status__in=(SMSMessageLog.Status.SUBMITTED, SMSMessageLog.Status.DELIVERED, SMSMessageLog.Status.UNKNOWN)).aggregate(total=Sum("free_credits"))["total"] or 0,
            },
            "bundles": SMSBundleSerializer(SMSBundle.objects.filter(is_active=True), many=True).data,
            "recent_messages": SMSMessageLogSerializer(messages[:30], many=True).data,
            "transactions": [],
            "recent_purchases": [],
            "can_manage": _can_view_financial_history(request.user, school, request),
        }
        if data["can_manage"]:
            data["transactions"] = SMSWalletTransactionSerializer(SMSWalletTransaction.objects.filter(school=school)[:50], many=True).data
            data["recent_purchases"] = SMSPurchaseSerializer(SMSPurchase.objects.filter(school=school)[:30], many=True).data
        return Response(data)


class SMSSendView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "sms_send"
    required_school_permission = "sms.send"

    def post(self, request, **kwargs):
        serializer = SMSSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "").strip()
        try:
            result = send_school_sms(
                school=_school(request), actor=request.user,
                recipients=serializer.validated_data["recipients"],
                message=serializer.validated_data["message"], idempotency_key=key,
            )
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])
            raise serializers.ValidationError(detail) from exc
        code = status.HTTP_200_OK if result.get("replayed") else status.HTTP_201_CREATED
        return Response(result, status=code)


class SMSPurchaseInitializeView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "sms.manage"

    def post(self, request, **kwargs):
        serializer = SMSPurchaseInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bundle = SMSBundle.objects.filter(pk=serializer.validated_data["bundle"], is_active=True).first()
        if bundle is None:
            raise serializers.ValidationError({"bundle": "Choose an available SMS bundle."})
        try:
            purchase = initialize_sms_purchase(
                school=_school(request), user=request.user, bundle=bundle,
                provider_name=serializer.validated_data["provider"],
            )
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        return Response(SMSPurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)


class SMSPurchaseDetailView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "sms.manage"

    def post(self, request, reference, **kwargs):
        purchase = SMSPurchase.objects.filter(school=_school(request), reference=reference).first()
        if purchase is None:
            raise Http404
        if purchase.status == SMSPurchase.Status.PENDING:
            try:
                purchase = verify_sms_purchase(
                    purchase,
                    transaction_id=request.data.get("transaction_id") or request.query_params.get("transaction_id", ""),
                )
            except (DjangoValidationError, ImproperlyConfigured) as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        wallet, _ = SMSWallet.objects.get_or_create(school=purchase.school)
        return Response({**SMSPurchaseSerializer(purchase).data, "purchased_balance": wallet.purchased_balance})


class SMSPaymentWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, provider_name, **kwargs):
        raw = request.body
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Invalid payment notification."}, status=400)
        data = payload.get("data") or {}
        event_type = ""
        if provider_name == "paystack":
            secret = settings.PAYSTACK_WEBHOOK_SECRET
            signature = request.headers.get("x-paystack-signature", "")
            expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest() if secret else ""
            valid = bool(secret and signature and hmac.compare_digest(signature, expected))
            reference = data.get("reference")
            transaction_id = data.get("reference")
            event_type = payload.get("event", "")
            event_id = f"{event_type}:{data.get('id') or reference or ''}"
        elif provider_name == "flutterwave":
            secret = settings.FLUTTERWAVE_WEBHOOK_SECRET
            signature = request.headers.get("verif-hash", "")
            valid = bool(secret and signature and hmac.compare_digest(signature, secret))
            reference = data.get("tx_ref") or (data.get("meta") or {}).get("edustacked_reference")
            transaction_id = data.get("id")
            event_type = payload.get("event", "")
            event_id = f"{event_type}:{data.get('id') or reference or ''}"
        else:
            return Response({"detail": "Unknown payment provider."}, status=404)
        if not valid:
            return Response({"detail": "Payment notification could not be verified."}, status=401)
        if not reference or not event_id.strip(":"):
            return Response({"detail": "Payment notification is missing its reference."}, status=400)
        purchase = SMSPurchase.objects.filter(provider=provider_name, reference=reference).first()
        if purchase is None:
            return Response({"received": True})
        event_id = event_id[:160]
        try:
            with transaction.atomic():
                event, created = SMSProviderEvent.objects.get_or_create(
                    provider=provider_name, event_id=event_id,
                    defaults={"payment": purchase, "event_type": str(event_type)[:80], "payload_hash": hashlib.sha256(raw).hexdigest()},
                )
                if not created:
                    return Response({"received": True, "duplicate": True})
                if provider_name == "paystack":
                    result = PaystackWebhookVerify.verify(purchase)
                else:
                    result = FlutterwaveProvider().verify(transaction_id)
                apply_sms_purchase_result(purchase, result)
                event.processed_at = timezone.now()
                event.save(update_fields=("processed_at",))
        except (DjangoValidationError, ImproperlyConfigured):
            return Response({"received": True, "reconciliation_required": True}, status=503)
        return Response({"received": True})


class PaystackWebhookVerify:
    @staticmethod
    def verify(purchase):
        from apps.billing.providers import PaystackProvider
        return PaystackProvider().verify(purchase.reference)


class TermiiDeliveryWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, **kwargs):
        if not termii_signature_is_valid(request.body, request.headers.get("x-termii-signature", "")):
            return Response({"detail": "Delivery notification could not be verified."}, status=401)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Invalid delivery notification."}, status=400)
        try:
            apply_delivery_report(payload)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"received": True})


def _range(request):
    params = {"start": request.query_params.get("from"), "end": request.query_params.get("to")}
    serializer = SMSDateRangeSerializer(data={key: value for key, value in params.items() if value})
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    today = timezone.localdate()
    end = values.get("end", today)
    start = values.get("start", end.replace(day=1))
    return start, end


def _message_cost(row, *, paid=False):
    total = row.actual_provider_cost_minor if row.actual_provider_cost_minor is not None else row.provider_cost_estimate_minor
    if not paid:
        return total
    if row.segments <= 0:
        return 0
    return int((Decimal(total) * Decimal(row.paid_credits) / Decimal(row.segments)).quantize(Decimal("1")))


def _school_sms_summary(school, start, end, config):
    messages = list(SMSMessageLog.objects.filter(school=school, created_at__date__gte=start, created_at__date__lte=end))
    eligible = [row for row in messages if row.status in (SMSMessageLog.Status.SUBMITTED, SMSMessageLog.Status.DELIVERED, SMSMessageLog.Status.UNKNOWN)]
    purchases = SMSPurchase.objects.filter(school=school, status=SMSPurchase.Status.SUCCESS, paid_at__date__gte=start, paid_at__date__lte=end)
    wallet, _ = SMSWallet.objects.get_or_create(school=school)
    allowance = ensure_monthly_allowance(school)
    return {
        "school_id": school.pk,
        "school_name": school.name,
        "school_status": school.verification_status,
        "messages": len(eligible),
        "segments": sum(row.segments for row in eligible),
        "free_used": sum(row.free_credits for row in eligible),
        "paid_used": sum(row.paid_credits for row in eligible),
        "free_remaining": max(0, allowance.allowance_credits - allowance.used_credits),
        "purchased_balance": wallet.purchased_balance,
        "bundle_purchases": purchases.count(),
        "cash_collected_minor": purchases.aggregate(total=Sum("amount_minor"))["total"] or 0,
        "provider_cost_minor": sum(_message_cost(row) for row in eligible),
        "paid_sales_value_consumed_minor": sum(row.paid_sales_value_minor for row in eligible),
        "paid_provider_cost_minor": sum(_message_cost(row, paid=True) for row in eligible),
        "failed_messages": sum(row.status == SMSMessageLog.Status.FAILED for row in messages),
        "delivered_messages": sum(row.status == SMSMessageLog.Status.DELIVERED for row in messages),
        "last_sms_at": max((row.created_at for row in messages), default=None),
        "sending_suspended": wallet.sending_suspended,
    }


class PlatformSMSOverviewView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        start, end = _range(request)
        config = platform_config()
        schools = School.objects.all().order_by("name")
        all_rows = [_school_sms_summary(school, start, end, config) for school in schools.iterator()]
        query = request.query_params.get("q", "").strip()
        rows = [row for row in all_rows if not query or query.casefold() in row["school_name"].casefold()]
        overview = {
            "from": start, "to": end,
            "total_segments_sent": sum(row["segments"] for row in all_rows),
            "free_credits_consumed": sum(row["free_used"] for row in all_rows),
            "paid_credits_consumed": sum(row["paid_used"] for row in all_rows),
            "delivered_messages": sum(row["delivered_messages"] for row in all_rows),
            "failed_messages": sum(row["failed_messages"] for row in all_rows),
            "sales_revenue_minor": sum(row["cash_collected_minor"] for row in all_rows),
            "provider_expenditure_minor": sum(row["provider_cost_minor"] for row in all_rows),
            "free_subsidy_cost_minor": sum(row["free_used"] for row in all_rows) * config.provider_cost_per_credit_minor,
            "paid_consumed_value_minor": sum(row["paid_sales_value_consumed_minor"] for row in all_rows),
            "paid_provider_cost_minor": sum(row["paid_provider_cost_minor"] for row in all_rows),
            "average_provider_cost_per_segment_minor": int((Decimal(sum(row["provider_cost_minor"] for row in all_rows)) / Decimal(sum(row["segments"] for row in all_rows))).quantize(Decimal("1"))) if sum(row["segments"] for row in all_rows) else 0,
            "average_paid_sale_value_per_credit_minor": int((Decimal(sum(row["paid_sales_value_consumed_minor"] for row in all_rows)) / Decimal(sum(row["paid_used"] for row in all_rows))).quantize(Decimal("1"))) if sum(row["paid_used"] for row in all_rows) else 0,
            "outstanding_credit_liability_minor": sum(SMSWallet.objects.filter(school_id=row["school_id"]).values_list("paid_value_balance_minor", flat=True).first() or 0 for row in all_rows),
            "active_schools": sum(row["messages"] > 0 for row in all_rows),
            "schools_count": School.objects.count(),
            "estimated_gross_profit_minor": sum(row["paid_sales_value_consumed_minor"] - row["paid_provider_cost_minor"] for row in all_rows),
        }
        return Response({"overview": overview, "schools": rows, "configuration": SMSPlatformConfigurationSerializer(config).data, "bundles": SMSBundleSerializer(SMSBundle.objects.all(), many=True).data})


class PlatformSMSConfigurationView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def patch(self, request, **kwargs):
        config = platform_config()
        serializer = SMSPlatformConfigurationSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(SMSPlatformConfigurationSerializer(config).data)


class PlatformSMSBundleListView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def post(self, request, **kwargs):
        serializer = SMSBundleManageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bundle = serializer.save()
        except IntegrityError as exc:
            raise serializers.ValidationError({"name": "A bundle with this name already exists."}) from exc
        return Response(SMSBundleManageSerializer(bundle).data, status=status.HTTP_201_CREATED)


class PlatformSMSBundleDetailView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def patch(self, request, pk, **kwargs):
        bundle = SMSBundle.objects.filter(pk=pk).first()
        if bundle is None:
            raise Http404
        serializer = SMSBundleManageSerializer(bundle, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            bundle = serializer.save()
        except IntegrityError as exc:
            raise serializers.ValidationError({"name": "A bundle with this name already exists."}) from exc
        return Response(SMSBundleManageSerializer(bundle).data)


class PlatformSMSSchoolDetailView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, pk, **kwargs):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            raise Http404
        start, end = _range(request)
        summary = _school_sms_summary(school, start, end, platform_config())
        return Response({
            **summary,
            "transactions": list(SMSWalletTransaction.objects.filter(school=school).values("id", "kind", "credits", "description", "reference_key", "created_at", "metadata")[:100]),
            "purchases": SMSPurchaseSerializer(SMSPurchase.objects.filter(school=school)[:100], many=True).data,
            "messages": SMSMessageLogSerializer(SMSMessageLog.objects.filter(school=school)[:100], many=True).data,
            "monthly_allowances": list(SMSMonthlyAllowance.objects.filter(school=school)[:12].values("month_start", "allowance_credits", "used_credits")),
        })

    def post(self, request, pk, action, **kwargs):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            raise Http404
        if action not in {"suspend", "resume"}:
            return Response({"detail": "Choose suspend or resume."}, status=400)
        reason = str(request.data.get("reason", "")).strip()
        if action == "suspend" and not reason:
            raise serializers.ValidationError({"reason": "Add a reason for pausing SMS sending."})
        with transaction.atomic():
            School.objects.select_for_update().get(pk=school.pk)
            wallet, _ = SMSWallet.objects.get_or_create(school=school)
            wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.sending_suspended = action == "suspend"
            wallet.suspension_reason = reason[:500] if action == "suspend" else ""
            wallet.suspended_at = timezone.now() if action == "suspend" else None
            wallet.save(update_fields=("sending_suspended", "suspension_reason", "suspended_at", "updated_at"))
        return Response({"detail": "SMS sending paused for this school." if action == "suspend" else "SMS sending resumed for this school.", "sending_suspended": wallet.sending_suspended, "reason": wallet.suspension_reason})
