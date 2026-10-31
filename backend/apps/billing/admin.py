from django.contrib import admin

from .models import CreditAccount, CreditPackage, CreditPayment, CreditTransaction, ReconciliationIssue, ReportCardBilling


@admin.register(CreditPackage)
class CreditPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "credits", "price_minor", "is_active", "display_order")
    list_editable = ("is_active", "display_order")
    search_fields = ("name",)


@admin.register(CreditAccount)
class CreditAccountAdmin(admin.ModelAdmin):
    list_display = ("school", "balance", "updated_at")
    readonly_fields = tuple(field.name for field in CreditAccount._meta.fields)
    list_select_related = ("school",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "school", "package_name", "credits", "amount_minor", "status", "created_at")
    list_filter = ("status", "provider", "created_at")
    search_fields = ("reference", "school__name")
    readonly_fields = tuple(field.name for field in CreditPayment._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ("school", "kind", "amount", "reference_key", "created_at")
    readonly_fields = tuple(field.name for field in CreditTransaction._meta.fields)
    list_select_related = ("school", "payment", "actor")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReportCardBilling)
class ReportCardBillingAdmin(admin.ModelAdmin):
    list_display = ("school", "student", "academic_session", "term", "charged_at", "legacy_waived")
    readonly_fields = tuple(field.name for field in ReportCardBilling._meta.fields)
    list_select_related = ("school", "student", "academic_session", "term")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReconciliationIssue)
class ReconciliationIssueAdmin(admin.ModelAdmin):
    list_display = ("kind", "school", "provider_reference", "status", "created_at")
    list_filter = ("status", "kind")
    readonly_fields = tuple(field.name for field in ReconciliationIssue._meta.fields)
