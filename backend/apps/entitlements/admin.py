from django.contrib import admin

from .models import ServiceEntitlement, ServicePlan


@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "service_code", "package_type", "student_capacity", "price_minor", "currency", "is_active")
    list_filter = ("service_code", "is_active", "currency")
    search_fields = ("name", "service_code", "package_type")


@admin.register(ServiceEntitlement)
class ServiceEntitlementAdmin(admin.ModelAdmin):
    list_display = ("school", "service_code", "package_type", "status", "starts_on", "expires_on", "payment_reference")
    list_filter = ("service_code", "status")
    search_fields = ("school__name", "payment_reference", "license_id")
    readonly_fields = ("id", "license_id", "signed_license", "created_at", "updated_at")
