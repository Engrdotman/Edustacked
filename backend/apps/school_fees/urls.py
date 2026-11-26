from django.urls import path

from .views import (
    BankListView, BachsSchoolConnectView, ConnectPaymentAccountView, FeeChargeListView, FeeIssueView,
    FeeNotificationRetryView, FeeScheduleDetailView, FeeScheduleListCreateView,
    FinanceOverviewView, ManualPaymentView, ParentFeeView, ParentPaymentDetailView,
    ParentPaymentInitializeView, ParentPaymentReceiptView, ParentReceiptOtpView,
    ParentStudentFeesView, PaymentReverseView, PaymentWebhookView,
    SchoolFeeSettingsView, SchoolPaymentListView, SchoolReceiptView,
)

urlpatterns = [
    path("school-fees/settings/", SchoolFeeSettingsView.as_view(), name="school-fee-settings"),
    path("school-fees/settings/banks/", BankListView.as_view(), name="school-fee-banks"),
    path("school-fees/settings/connect/", ConnectPaymentAccountView.as_view(), name="school-fee-connect-account"),
    path("school-fees/settings/bachs-connect/", BachsSchoolConnectView.as_view(), name="school-fee-bachs-connect"),
    path("school-fees/overview/", FinanceOverviewView.as_view(), name="school-fee-overview"),
    path("school-fees/schedules/", FeeScheduleListCreateView.as_view(), name="school-fee-schedules"),
    path("school-fees/schedules/<int:pk>/", FeeScheduleDetailView.as_view(), name="school-fee-schedule-detail"),
    path("school-fees/schedules/issue/", FeeIssueView.as_view(), name="school-fee-issue"),
    path("school-fees/charges/", FeeChargeListView.as_view(), name="school-fee-charges"),
    path("school-fees/payments/", SchoolPaymentListView.as_view(), name="school-fee-payments"),
    path("school-fees/payments/manual/", ManualPaymentView.as_view(), name="school-fee-manual-payment"),
    path("school-fees/payments/<str:reference>/reverse/", PaymentReverseView.as_view(), name="school-fee-payment-reverse"),
    path("school-fees/payments/<str:reference>/receipt/", SchoolReceiptView.as_view(), name="school-fee-school-receipt"),
    path("school-fees/notifications/<int:pk>/retry/", FeeNotificationRetryView.as_view(), name="school-fee-notification-retry"),
    path("school-fees/webhooks/<str:provider_name>/", PaymentWebhookView.as_view(), name="school-fee-webhook"),
    path("parent/students/<int:student_id>/fees/", ParentStudentFeesView.as_view(), name="parent-student-fees"),
    path("parent/fees/payments/initialize/", ParentPaymentInitializeView.as_view(), name="parent-fee-payment-init"),
    path("parent/fees/payments/<str:reference>/", ParentPaymentDetailView.as_view(), name="parent-fee-payment-detail"),
    path("parent/fees/payments/<str:reference>/receipt/", ParentPaymentReceiptView.as_view(), name="parent-fee-payment-receipt"),
    path("parent/fees/payments/<str:reference>/receipt/verify/", ParentReceiptOtpView.as_view(), name="parent-fee-receipt-verify"),
]
