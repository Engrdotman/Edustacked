from django.urls import path

from .payment_webhooks import FlutterwaveWebhookView
from .views import database_health_check, health_check

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("health/database/", database_health_check, name="database-health-check"),
    path("webhooks/flutterwave/", FlutterwaveWebhookView.as_view(), name="flutterwave-webhook"),
]
