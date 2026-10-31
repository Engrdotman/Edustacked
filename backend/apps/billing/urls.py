from django.urls import path

from .views import (
    BillingOverviewView, CreditPackageListView, PaystackWebhookView,
    PaymentDetailView, PaymentHistoryView, PlatformBillingAdjustmentView,
    PlatformBillingIssuesView, PurchaseInitializeView,
    ReportCardBillingHistoryView, TransactionHistoryView,
)

urlpatterns = [
    path("billing/credits/", BillingOverviewView.as_view(), name="billing-credits"),
    path("billing/packages/", CreditPackageListView.as_view(), name="billing-packages"),
    path("billing/purchases/", PurchaseInitializeView.as_view(), name="billing-purchase-init"),
    path("billing/payments/", PaymentHistoryView.as_view(), name="billing-payments"),
    path("billing/payments/<str:reference>/", PaymentDetailView.as_view(), name="billing-payment-detail"),
    path("billing/transactions/", TransactionHistoryView.as_view(), name="billing-transactions"),
    path("billing/report-card-records/", ReportCardBillingHistoryView.as_view(), name="billing-report-cards"),
    path("billing/paystack/webhook/", PaystackWebhookView.as_view(), name="billing-paystack-webhook"),
    path("platform/billing/adjustments/", PlatformBillingAdjustmentView.as_view(), name="platform-billing-adjustment"),
    path("platform/billing/issues/", PlatformBillingIssuesView.as_view(), name="platform-billing-issues"),
    path("platform/billing/issues/<int:pk>/resolve/", PlatformBillingIssuesView.as_view(), name="platform-billing-issue-resolve"),
]
