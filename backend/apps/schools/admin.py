from django.contrib import admin

from .models import School, SchoolMembership, SchoolOnboardingProgress, SchoolSettings, SchoolVerificationEvent


class SchoolSettingsInline(admin.StackedInline):
    model = SchoolSettings
    extra = 0
    can_delete = False


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    inlines = (SchoolSettingsInline,)

    def get_readonly_fields(self, request, obj=None):
        return ("slug",) if obj else ()


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "school__name")


@admin.register(SchoolOnboardingProgress)
class SchoolOnboardingProgressAdmin(admin.ModelAdmin):
    list_display = ("school", "current_step", "updated_by", "updated_at")
    readonly_fields = ("school", "current_step", "updated_by", "updated_at")


@admin.register(SchoolVerificationEvent)
class SchoolVerificationEventAdmin(admin.ModelAdmin):
    list_display = ("school", "actor", "action", "from_status", "to_status", "created_at")
    list_filter = ("action", "from_status", "to_status")
    readonly_fields = tuple(field.name for field in SchoolVerificationEvent._meta.fields)
