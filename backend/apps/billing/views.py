import json

from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError
from django.db import transaction
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
from .serializers import (
    AdjustmentSerializer, CreditPackageSerializer, CreditPaymentSerializer,
    CreditTransactionSerializer, IssueResolutionSerializer, PurchaseSerializer,
    ReconciliationIssueSerializer, ReportCardBillingSerializer,
)
from .services import (
    apply_provider_result, current_balance, initialize_purchase,
    paystack_signature_is_valid, platform_adjustment,
)
from .providers import PaystackProvider


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
            payment = initialize_purchase(school, request.user, package)
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        return Response(CreditPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


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
