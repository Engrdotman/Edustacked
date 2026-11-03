from django.contrib import admin

from .models import (
    AnswerSaveRequest,
    ImportedExamination,
    ImportLog,
    LocalExamSession,
    LocalLicenseVerification,
    LocalStudentAnswer,
    LocalStudentCredential,
    LocalSubmission,
    StudentAccessToken,
    SyncLog,
    SyncOutbox,
)


@admin.register(LocalStudentCredential)
class LocalStudentCredentialAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "display_name", "central_student_id", "is_active", "locked_until")
    search_fields = ("admission_number", "display_name")
    readonly_fields = ("password_hash", "failed_login_attempts", "locked_until", "created_at")


@admin.register(ImportedExamination)
class ImportedExaminationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "school_id", "version", "status", "imported_at")
    list_filter = ("school_id", "status")
    readonly_fields = tuple(field.name for field in ImportedExamination._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(LocalExamSession)
class LocalExamSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "exam", "status", "started_at", "expires_at", "submitted_at")
    list_filter = ("status", "exam")
    search_fields = ("student__admission_number", "student__display_name")
    readonly_fields = tuple(field.name for field in LocalExamSession._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SyncOutbox)
class SyncOutboxAdmin(admin.ModelAdmin):
    list_display = ("event_id", "session", "status", "retry_count", "last_attempt_at", "synced_at")
    list_filter = ("status",)
    readonly_fields = tuple(field.name for field in SyncOutbox._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LocalStudentAnswer, LocalSubmission, SyncLog, LocalLicenseVerification, AnswerSaveRequest)
class ImmutableAuditAdmin(admin.ModelAdmin):
    readonly_fields = tuple(field.name for field in [])

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StudentAccessToken, ImportLog)
class RestrictedAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
