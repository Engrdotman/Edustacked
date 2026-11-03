from django.contrib import admin

from .models import (
    CbtExaminationPackage, CbtResult, CbtResultCorrection, CbtSyncedSubmission, CbtSyncConflict, LocalCbtServerCredential,
    LocalCbtSyncEvent, Examination, ExaminationAssignment, ExaminationQuestion, Question, QuestionOption,
)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "school", "subject", "class_level", "question_type", "difficulty", "status")
    list_filter = ("school", "subject", "class_level", "question_type", "difficulty", "status")
    search_fields = ("text", "topic")
    inlines = (QuestionOptionInline,)


class ExaminationQuestionInline(admin.TabularInline):
    model = ExaminationQuestion
    extra = 0
    readonly_fields = ("prompt_snapshot", "options_snapshot", "is_snapshot")


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "subject", "class_level", "academic_session", "status", "starts_at")
    list_filter = ("school", "status", "academic_session", "subject")
    search_fields = ("title", "description")
    inlines = (ExaminationQuestionInline,)


@admin.register(ExaminationAssignment)
class ExaminationAssignmentAdmin(admin.ModelAdmin):
    list_display = ("examination", "student", "status", "assigned_by", "assigned_at")
    list_filter = ("status", "examination__school")
    search_fields = ("student__admission_number", "examination__title")


@admin.register(LocalCbtServerCredential)
class LocalCbtServerCredentialAdmin(admin.ModelAdmin):
    list_display = ("school", "name", "is_active", "last_seen_at", "created_at")
    list_filter = ("is_active", "school")
    readonly_fields = ("token_hash", "created_at", "last_seen_at")


@admin.register(CbtExaminationPackage)
class CbtExaminationPackageAdmin(admin.ModelAdmin):
    list_display = ("examination", "school", "version", "payload_hash", "created_at")
    readonly_fields = ("package_id", "payload_hash", "signed_payload", "created_at")


@admin.register(LocalCbtSyncEvent)
class LocalCbtSyncEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "school", "examination", "assignment", "status", "received_at")
    list_filter = ("school", "status")
    readonly_fields = tuple(field.name for field in LocalCbtSyncEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CbtSyncedSubmission)
class CbtSyncedSubmissionAdmin(admin.ModelAdmin):
    list_display = ("school", "examination", "assignment", "local_session_id", "submitted_at", "received_at")
    list_filter = ("school", "examination")
    readonly_fields = tuple(field.name for field in CbtSyncedSubmission._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CbtSyncConflict)
class CbtSyncConflictAdmin(admin.ModelAdmin):
    list_display = ("event", "reason", "created_at")
    readonly_fields = tuple(field.name for field in CbtSyncConflict._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CbtResult)
class CbtResultAdmin(admin.ModelAdmin):
    list_display = ("assignment", "examination", "status", "score", "maximum_score", "percentage", "passed", "submitted_at")
    list_filter = ("school", "status", "passed", "examination__academic_session", "examination__subject")
    search_fields = ("assignment__student__admission_number", "assignment__student__first_name", "examination__title")
    readonly_fields = tuple(field.name for field in CbtResult._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CbtResultCorrection)
class CbtResultCorrectionAdmin(admin.ModelAdmin):
    list_display = ("result", "corrected_by", "reason", "created_at")
    readonly_fields = tuple(field.name for field in CbtResultCorrection._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
