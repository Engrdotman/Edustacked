from django.urls import path

from .views import (
    BachsWebhookView, BillingOverviewView, CreditPackageListView, FlutterwaveWebhookView, PaystackWebhookView,
    PaymentDetailView, PaymentHistoryView, PlatformBillingAdjustmentView,
    PlatformBillingIssuesView, PurchaseInitializeView,
    ReportCardBillingHistoryView, TransactionHistoryView,
    PlatformCreditPackageListView, PlatformCreditPackageDetailView,
    StaffSeatPurchaseView, StaffSeatCapacityView, PlatformStaffSeatPlanView,
)

urlpatterns = [
    path("billing/credits/", BillingOverviewView.as_view(), name="billing-credits"),
    path("billing/packages/", CreditPackageListView.as_view(), name="billing-packages"),
    path("platform/billing/packages/", PlatformCreditPackageListView.as_view(), name="platform-credit-packages"),
    path("platform/billing/packages/<int:pk>/", PlatformCreditPackageDetailView.as_view(), name="platform-credit-package-detail"),
    path("platform/billing/staff-seats/", PlatformStaffSeatPlanView.as_view(), name="platform-staff-seat-plan"),
    path("billing/purchases/", PurchaseInitializeView.as_view(), name="billing-purchase-init"),
    path("billing/staff-seats/capacity/", StaffSeatCapacityView.as_view(), name="billing-staff-seats-capacity"),
    path("billing/staff-seats/purchase/", StaffSeatPurchaseView.as_view(), name="billing-staff-seats-purchase"),
    path("billing/payments/", PaymentHistoryView.as_view(), name="billing-payments"),
    path("billing/payments/<str:reference>/", PaymentDetailView.as_view(), name="billing-payment-detail"),
    path("billing/transactions/", TransactionHistoryView.as_view(), name="billing-transactions"),
    path("billing/report-card-records/", ReportCardBillingHistoryView.as_view(), name="billing-report-cards"),
    path("billing/paystack/webhook/", PaystackWebhookView.as_view(), name="billing-paystack-webhook"),
    path("billing/flutterwave/webhook/", FlutterwaveWebhookView.as_view(), name="billing-flutterwave-webhook"),
    path("billing/bachs/webhook/", BachsWebhookView.as_view(), name="billing-bachs-webhook"),
    path("platform/billing/adjustments/", PlatformBillingAdjustmentView.as_view(), name="platform-billing-adjustment"),
    path("platform/billing/issues/", PlatformBillingIssuesView.as_view(), name="platform-billing-issues"),
    path("platform/billing/issues/<int:pk>/resolve/", PlatformBillingIssuesView.as_view(), name="platform-billing-issue-resolve"),
]
