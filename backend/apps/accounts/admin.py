from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import DemoRequest, EmailVerificationToken, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Verification", {"fields": ("phone_number", "email_verified_at", "phone_verified_at")}),)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("selector", "user", "expires_at", "consumed_at", "created_at")
    readonly_fields = ("selector", "user", "token_hash", "expires_at", "consumed_at", "created_at")


@admin.register(DemoRequest)
class DemoRequestAdmin(admin.ModelAdmin):
    list_display = ("school_name", "administrator_name", "email", "phone_number", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("school_name", "administrator_name", "email", "phone_number")
