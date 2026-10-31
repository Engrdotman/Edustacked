from django.contrib import admin

from .models import StaffProfile, TeacherAssignment, TeacherProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "first_name", "last_name", "job_title", "school", "status")
    list_filter = ("school", "status", "employment_type")
    search_fields = ("staff_number", "first_name", "last_name", "work_email")


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("staff", "school", "specialization", "teaching_status")
    list_filter = ("school", "teaching_status")


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "academic_session", "class_level", "class_arm", "subject", "status")
    list_filter = ("school", "academic_session", "status", "subject")
    search_fields = ("teacher__staff__staff_number", "teacher__staff__first_name", "teacher__staff__last_name")
