from django.urls import path

from .views import (
    PlatformSMSBundleDetailView, PlatformSMSBundleListView,
    PlatformSMSConfigurationView, PlatformSMSOverviewView,
    PlatformSMSSchoolDetailView, SMSOverviewView, SMSPaymentWebhookView,
    SMSPurchaseDetailView, SMSPurchaseInitializeView, SMSSendView,
    TermiiDeliveryWebhookView,
)

urlpatterns = [
    path("sms/overview/", SMSOverviewView.as_view(), name="sms-overview"),
    path("sms/send/", SMSSendView.as_view(), name="sms-send"),
    path("sms/purchases/", SMSPurchaseInitializeView.as_view(), name="sms-purchase"),
    path("sms/purchases/<str:reference>/verify/", SMSPurchaseDetailView.as_view(), name="sms-purchase-verify"),
    path("sms/webhooks/payment/<str:provider_name>/", SMSPaymentWebhookView.as_view(), name="sms-payment-webhook"),
    path("sms/webhooks/termii/", TermiiDeliveryWebhookView.as_view(), name="sms-termii-webhook"),
    path("platform/sms/overview/", PlatformSMSOverviewView.as_view(), name="platform-sms-overview"),
    path("platform/sms/configuration/", PlatformSMSConfigurationView.as_view(), name="platform-sms-config"),
    path("platform/sms/bundles/", PlatformSMSBundleListView.as_view(), name="platform-sms-bundles"),
    path("platform/sms/bundles/<int:pk>/", PlatformSMSBundleDetailView.as_view(), name="platform-sms-bundle-detail"),
    path("platform/sms/schools/<int:pk>/", PlatformSMSSchoolDetailView.as_view(), name="platform-sms-school"),
    path("platform/sms/schools/<int:pk>/<str:action>/", PlatformSMSSchoolDetailView.as_view(), name="platform-sms-school-action"),
]
