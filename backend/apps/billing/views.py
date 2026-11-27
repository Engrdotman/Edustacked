import json

from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.models import School
from apps.schools.permissions import HasSchoolPermission, IsPlatformSuperadmin
from apps.schools.tenancy import resolve_authorized_school

from .models import CreditAccount, CreditPackage, CreditPayment, CreditTransaction, ReconciliationIssue, ReportCardBilling
from .models import StaffSeatAccount, StaffSeatPlan
from .serializers import (
    AdjustmentSerializer, CreditPackageSerializer, CreditPaymentSerializer,
    CreditTransactionSerializer, IssueResolutionSerializer, PurchaseSerializer,
    ReconciliationIssueSerializer, ReportCardBillingSerializer, StaffSeatPurchaseSerializer, StaffSeatPlanSerializer,
)
from .services import (
    apply_provider_result, bachs_signature_is_valid, current_balance, initialize_staff_seat_purchase,
    flutterwave_signature_is_valid,
    initialize_purchase, paystack_signature_is_valid, platform_adjustment,
)
from .providers import BachsProvider, FlutterwaveProvider, PaystackProvider


class BillingPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class SchoolBillingView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "billing.view"

    def school(self, request):
        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))


class BillingOverviewView(SchoolBillingView):
    def get(self, request, **kwargs):
        school = self.school(request)
        return Response({"balance": current_balance(school), "consumption_rule": "One credit for each student's first finalized report card per academic term. Preview, download, reprint, and later revisions are free."})


class CreditPackageListView(SchoolBillingView):
    def get(self, request, **kwargs):
        self.school(request)
        packages = CreditPackage.objects.filter(is_active=True)
        return Response(CreditPackageSerializer(packages, many=True).data)


class PlatformCreditPackageListView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        return Response(CreditPackageSerializer(CreditPackage.objects.all(), many=True).data)

    def post(self, request, **kwargs):
        serializer = CreditPackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            package = serializer.save()
        except IntegrityError as exc:
            raise serializers.ValidationError({"name": "A package with this name already exists."}) from exc
        return Response(CreditPackageSerializer(package).data, status=status.HTTP_201_CREATED)


class PlatformCreditPackageDetailView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def patch(self, request, pk, **kwargs):
        package = CreditPackage.objects.filter(pk=pk).first()
        if package is None:
            raise Http404
        serializer = CreditPackageSerializer(package, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            package = serializer.save()
        except IntegrityError as exc:
            raise serializers.ValidationError({"name": "A package with this name already exists."}) from exc
        return Response(CreditPackageSerializer(package).data)


class PurchaseInitializeView(SchoolBillingView):
    required_school_permission = "billing.purchase"

    def post(self, request, **kwargs):
        school = self.school(request)
        serializer = PurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = CreditPackage.objects.filter(pk=serializer.validated_data["package"], is_active=True).first()
        if package is None:
            raise serializers.ValidationError({"package": "Select an active credit package."})
        try:
            payment = initialize_purchase(school, request.user, package, serializer.validated_data["provider"])
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        return Response(CreditPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class StaffSeatCapacityView(SchoolBillingView):
    required_school_permission = "staff.view"

    def get(self, request, **kwargs):
        school = self.school(request)
        plan = StaffSeatPlan.current()
        account, _ = StaffSeatAccount.objects.get_or_create(school=school)
        from apps.staff.models import StaffProfile
        active_count = StaffProfile.objects.filter(school=school).exclude(status=StaffProfile.Status.FORMER).count()
        return Response({"included_seats": plan.included_seats, "purchased_seats": account.purchased_seats, "staff_count": active_count, "seat_limit": plan.included_seats + account.purchased_seats, "additional_seat_price_minor": plan.additional_seat_price_minor})


class StaffSeatPurchaseView(SchoolBillingView):
    required_school_permission = "billing.purchase"

    def post(self, request, **kwargs):
        school = self.school(request)
        serializer = StaffSeatPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = initialize_staff_seat_purchase(school, request.user, serializer.validated_data["seats"], serializer.validated_data["provider"])
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        return Response(CreditPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PlatformStaffSeatPlanView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        return Response(StaffSeatPlanSerializer(StaffSeatPlan.current()).data)

    def patch(self, request, **kwargs):
        plan = StaffSeatPlan.current()
        serializer = StaffSeatPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PaymentHistoryView(SchoolBillingView):
    def get(self, request, **kwargs):
        school = self.school(request)
        return self.paginate(CreditPayment.objects.filter(school=school), request)

    @staticmethod
    def paginate(queryset, request):
        paginator = BillingPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(CreditPaymentSerializer(page, many=True).data)


class TransactionHistoryView(SchoolBillingView):
    def get(self, request, **kwargs):
        school = self.school(request)
        paginator = BillingPagination()
        page = paginator.paginate_queryset(CreditTransaction.objects.filter(school=school), request)
        return paginator.get_paginated_response(CreditTransactionSerializer(page, many=True).data)


class ReportCardBillingHistoryView(SchoolBillingView):
    def get(self, request, **kwargs):
        school = self.school(request)
        paginator = BillingPagination()
        page = paginator.paginate_queryset(ReportCardBilling.objects.filter(school=school).select_related("student", "academic_session", "term"), request)
        return paginator.get_paginated_response(ReportCardBillingSerializer(page, many=True).data)


class PaymentDetailView(SchoolBillingView):
    def get_payment(self, request, reference):
        school = self.school(request)
        return CreditPayment.objects.filter(school=school, reference=reference).first()

    def get(self, request, reference, **kwargs):
        payment = self.get_payment(request, reference)
        if payment is None:
            return Response({"detail": "Payment was not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CreditPaymentSerializer(payment).data)

    def post(self, request, reference, **kwargs):
        payment = self.get_payment(request, reference)
        if payment is None:
            return Response({"detail": "Payment was not found."}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == CreditPayment.Status.PENDING:
            try:
                if payment.provider == "flutterwave":
                    transaction_id = request.data.get("transaction_id") or payment.provider_transaction_id
                    if not transaction_id:
                        raise serializers.ValidationError({"payment": "Flutterwave transaction ID is required to verify this checkout."})
                    data = FlutterwaveProvider().verify(transaction_id)
                elif payment.provider == "bachs":
                    checkout_id = request.data.get("checkout_id") or payment.provider_transaction_id
                    data = BachsProvider().verify(checkout_id)
                else:
                    data = PaystackProvider().verify(payment.reference)
                payment = apply_provider_result(payment, data)
            except (DjangoValidationError, ImproperlyConfigured) as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        result = CreditPaymentSerializer(payment).data
        result["balance"] = current_balance(payment.school)
        return Response(result)


class PaystackWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request, **kwargs):
        if not paystack_signature_is_valid(request.body, request.headers.get("x-paystack-signature", "")):
            return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            event = json.loads(request.body)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(event, dict) or not isinstance(event.get("data", {}), dict):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)
        data = event.get("data") or {}
        reference = data.get("reference") or data.get("transaction_reference")
        payment = CreditPayment.objects.filter(provider="paystack", reference=reference).first()
        if payment is None:
            # Valid provider event but not an order managed by this installation.
            return Response({"received": True})
        if event.get("event") == "charge.success":
            try:
                apply_provider_result(payment, data)
            except DjangoValidationError as exc:
                ReconciliationIssue.objects.get_or_create(
                    kind="payment_mismatch", provider_reference=str(reference or ""),
                    defaults={"school": payment.school, "payment": payment,
                              "description": "Signed provider success did not match the internal payment amount, currency, email, or reference. Manual reconciliation is required."},
                )
                return Response({"received": True, "reconciliation_required": True})
        elif event.get("event") in {"refund.pending", "refund.processing", "refund.processed", "refund.failed", "refund.needs-attention", "charge.dispute.create", "charge.dispute.resolve"}:
            if event.get("event") == "refund.processed":
                apply_provider_result(payment, {"status": "reversed", "reference": reference})
            ReconciliationIssue.objects.get_or_create(
                kind=event["event"], provider_reference=str(reference or ""),
                defaults={"school": payment.school, "payment": payment,
                          "description": f"Paystack reported {event['event']}. Review the transaction and approved refund policy."},
            )
        return Response({"received": True})


class FlutterwaveWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, **kwargs):
        if not flutterwave_signature_is_valid(request.headers.get("verif-hash", "")):
            return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            event = json.loads(request.body)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)

        data = event["data"]
        if event.get("event") != "charge.completed":
            return Response({"received": True})
        reference = data.get("tx_ref")
        transaction_id = data.get("id")
        if not reference or not str(transaction_id or "").isdigit():
            return Response({"detail": "Payment notification is missing its transaction reference."}, status=status.HTTP_400_BAD_REQUEST)
        payment = CreditPayment.objects.filter(provider="flutterwave", reference=reference).select_related("school").first()
        if payment is None:
            return Response({"received": True})
        # Once a verified charge is applied, repeated delivery of the same
        # success notification needs no extra provider API request.
        if payment.status in {CreditPayment.Status.SUCCESS, CreditPayment.Status.REVERSED}:
            return Response({"received": True, "duplicate": True})

        # Never grant credits from webhook fields alone; recheck the transaction with Flutterwave.
        try:
            verified = FlutterwaveProvider().verify(transaction_id)
        except (DjangoValidationError, ImproperlyConfigured):
            # Ask Flutterwave to retry transient verification/configuration failures.
            return Response({"detail": "Payment verification is temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            apply_provider_result(payment, verified)
        except DjangoValidationError:
            ReconciliationIssue.objects.get_or_create(
                kind="payment_mismatch", provider_reference=str(reference)[:100],
                defaults={"school": payment.school, "payment": payment,
                          "description": "Signed Flutterwave transaction did not match the internal credit purchase amount, currency, or reference. Manual reconciliation is required."},
            )
            return Response({"received": True, "reconciliation_required": True})
        return Response({"received": True})


class BachsWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, **kwargs):
        if not bachs_signature_is_valid(request.body, request.headers):
            return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            event = json.loads(request.body)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
            return Response({"detail": "Invalid event body."}, status=status.HTTP_400_BAD_REQUEST)
        event_data = event["data"]
        reference = str(event_data.get("reference") or "").strip()
        if not reference:
            return Response({"detail": "Payment notification is missing its reference."}, status=status.HTTP_400_BAD_REQUEST)

        # Bachs uses this one signed endpoint for platform purchases and direct
        # charges from connected school accounts. A webhook is only a signal to
        # verify; the signed payload itself never updates a balance.
        credit_payment = CreditPayment.objects.filter(provider="bachs", reference=reference).select_related("school").first()
        if credit_payment is not None:
            payment_kind, payment = "credits", credit_payment
        else:
            from apps.school_fees.models import SchoolFeePayment
            fee_payment = SchoolFeePayment.objects.filter(
                provider="bachs", reference=reference, channel=SchoolFeePayment.Channel.ONLINE,
            ).select_related("school").first()
            if fee_payment is not None:
                payment_kind, payment = "school_fees", fee_payment
            else:
                from apps.sms_management.models import SMSPurchase
                sms_purchase = SMSPurchase.objects.filter(provider="bachs", reference=reference).select_related("school").first()
                if sms_purchase is None:
                    return Response({"received": True})
                payment_kind, payment = "sms", sms_purchase

        event_type = str(event.get("type") or event.get("event") or "").lower()
        if event_type in {"checkout.expired", "collection.failed"}:
            if payment_kind == "credits":
                apply_provider_result(payment, {"status": "failed", "reference": reference})
            elif payment_kind == "school_fees":
                from apps.school_fees.models import SchoolFeePayment
                with transaction.atomic():
                    locked = SchoolFeePayment.objects.select_for_update().get(pk=payment.pk)
                    if locked.status == SchoolFeePayment.Status.PENDING:
                        locked.status = SchoolFeePayment.Status.FAILED
                        locked.save(update_fields=("status", "updated_at"))
            else:
                from apps.sms_management.services import apply_sms_purchase_result
                apply_sms_purchase_result(payment, {"status": "failed", "reference": reference})
            return Response({"received": True})

        if event_type not in {"checkout.completed", "collection.succeeded"}:
            return Response({"received": True})
        if event_type == "checkout.completed" and str(event_data.get("payment_status") or "").lower() not in {"paid", "succeeded"}:
            # A completed checkout can be a setup or a no-payment checkout.
            return Response({"received": True, "payment_collected": False})

        checkout_id = str(event_data.get("checkout_id") or "").strip()
        if not checkout_id:
            checkout_id = str(
                payment.provider_metadata.get("checkout_id")
                if payment_kind == "school_fees"
                else payment.provider_transaction_id
            ).strip()
        if payment.status in {"success", "partially_reversed", "reversed", "refunded"}:
            return Response({"received": True, "duplicate": True})
        if not checkout_id:
            return Response({"detail": "Payment notification is missing its checkout ID."}, status=status.HTTP_400_BAD_REQUEST)

        connected_account_id = ""
        if payment_kind == "school_fees":
            connected_account_id = str(payment.provider_metadata.get("provider_account_id") or "")
            if not connected_account_id:
                return Response({"detail": "School payment is missing its connected account."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            verified = BachsProvider().verify(checkout_id, connected_account_id=connected_account_id)
        except (DjangoValidationError, ImproperlyConfigured):
            # Transient provider failures should be retried by Bachs.
            return Response({"detail": "Bachs confirmation is temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if verified.get("status") == "pending":
            return Response({"received": True, "payment_collected": False})

        try:
            if payment_kind == "credits":
                apply_provider_result(payment, verified)
            elif payment_kind == "school_fees":
                from apps.school_fees.services import confirm_online_payment
                confirm_online_payment(payment, verified)
            else:
                from apps.sms_management.services import apply_sms_purchase_result
                apply_sms_purchase_result(payment, verified)
        except DjangoValidationError:
            ReconciliationIssue.objects.get_or_create(
                kind="bachs_payment_mismatch", provider_reference=reference[:100],
                defaults={
                    "school": payment.school,
                    "payment": payment if payment_kind == "credits" else None,
                    "description": "Bachs confirmed a checkout that did not match this EDUstacked order's reference, amount, or currency. No balance was updated; review this payment manually.",
                },
            )
            return Response({"received": True, "reconciliation_required": True})
        return Response({"received": True})


class PlatformBillingAdjustmentView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def post(self, request, **kwargs):
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = School.objects.filter(pk=data["school"], is_active=True).first()
        if school is None:
            raise serializers.ValidationError({"school": "Select an active school."})
        try:
            entry = platform_adjustment(school, request.user, data["amount"], data["reason"], data["reference_key"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response(CreditTransactionSerializer(entry).data, status=status.HTTP_201_CREATED)


class PlatformBillingIssuesView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformSuperadmin)

    def get(self, request, **kwargs):
        paginator = BillingPagination()
        page = paginator.paginate_queryset(ReconciliationIssue.objects.filter(status=ReconciliationIssue.Status.OPEN).select_related("school", "payment"), request)
        return paginator.get_paginated_response(ReconciliationIssueSerializer(page, many=True).data)

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        issue = ReconciliationIssue.objects.select_for_update().filter(pk=pk, status=ReconciliationIssue.Status.OPEN).first()
        if issue is None:
            return Response({"detail": "Open issue was not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = IssueResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue.status = ReconciliationIssue.Status.RESOLVED
        issue.resolution = serializer.validated_data["resolution"]
        issue.resolved_by = request.user
        issue.resolved_at = timezone.now()
        issue.save(update_fields=("status", "resolution", "resolved_by", "resolved_at"))
        return Response(ReconciliationIssueSerializer(issue).data)
