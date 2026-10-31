from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, ClassSubject, Subject
from apps.accounts.models import User
from apps.schools.models import SchoolMembership

from .models import StaffProfile, TeacherAssignment, TeacherProfile


class SafeStaffSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This record conflicts with existing school data.") from exc

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                previous_status = instance.status
                updated = super().update(instance, validated_data)
                if previous_status == StaffProfile.Status.ACTIVE and updated.status != StaffProfile.Status.ACTIVE:
                    teacher = getattr(updated, "teacher_profile", None)
                    if teacher:
                        teacher.teaching_status = TeacherProfile.TeachingStatus.INACTIVE
                        teacher.save()
                        today = timezone.localdate()
                        for assignment in teacher.assignments.filter(status=TeacherAssignment.Status.ACTIVE).select_related("academic_session"):
                            assignment.status = TeacherAssignment.Status.ENDED if today >= assignment.start_date else TeacherAssignment.Status.CANCELLED
                            assignment.end_date = min(today, assignment.academic_session.end_date)
                            if assignment.end_date < assignment.start_date:
                                assignment.end_date = assignment.start_date
                            assignment.save()
                return updated
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This record conflicts with existing school data.") from exc


class StaffDirectorySerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    is_teacher = serializers.SerializerMethodField()
    teacher_status = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = ("id", "staff_number", "first_name", "middle_name", "last_name", "display_name", "job_title", "department", "status", "is_teacher", "teacher_status", "teacher_id")
        read_only_fields = fields

    def get_display_name(self, obj):
        return " ".join(part for part in (obj.first_name, obj.middle_name, obj.last_name) if part)

    def get_is_teacher(self, obj):
        return hasattr(obj, "teacher_profile")

    def get_teacher_status(self, obj):
        teacher = getattr(obj, "teacher_profile", None)
        return teacher.teaching_status if teacher else None

    def get_teacher_id(self, obj):
        teacher = getattr(obj, "teacher_profile", None)
        return teacher.pk if teacher else None


class StaffProfileSerializer(SafeStaffSerializer):
    school = serializers.IntegerField(source="school_id", read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.none(), required=False, allow_null=True)
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = (
            "id", "school", "user", "has_login", "staff_number", "first_name", "middle_name", "last_name",
            "work_email", "phone", "job_title", "department", "employment_type", "employment_start_date",
            "employment_end_date", "status", "photo", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "has_login", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        self.fields["user"].queryset = User.objects.filter(school_memberships__school=school, school_memberships__is_active=True).distinct() if school else User.objects.none()

    def get_has_login(self, obj):
        return bool(obj.user_id)

    def validate_user(self, user):
        school = self.context["school"]
        if user and not SchoolMembership.objects.filter(user=user, school=school, is_active=True).exists():
            raise serializers.ValidationError("Link only an account with an active membership in this school.")
        duplicate = StaffProfile.objects.filter(school=school, user=user).exclude(pk=getattr(self.instance, "pk", None)).exists() if user else False
        if duplicate:
            raise serializers.ValidationError("This account is already linked to a staff profile in this school.")
        return user

    def validate_staff_number(self, value):
        value = value.strip()
        school = self.context["school"]
        if StaffProfile.objects.filter(school=school, staff_number__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("This staff number is already used in this school.")
        return value


class TeacherProfileSerializer(SafeStaffSerializer):
    staff = serializers.PrimaryKeyRelatedField(queryset=StaffProfile.objects.none(), required=False)
    staff_name = serializers.SerializerMethodField()
    staff_number = serializers.CharField(source="staff.staff_number", read_only=True)

    class Meta:
        model = TeacherProfile
        fields = ("id", "staff", "staff_number", "staff_name", "qualification_summary", "specialization", "teaching_status", "created_at", "updated_at")
        read_only_fields = ("id", "staff_number", "staff_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        self.fields["staff"].queryset = StaffProfile.objects.filter(school=school) if school else StaffProfile.objects.none()

    def get_staff_name(self, obj):
        return f"{obj.staff.first_name} {obj.staff.last_name}"

    def create(self, validated_data):
        validated_data["school_id"] = self.context["school"].pk
        return super().create(validated_data)

    def update(self, instance, validated_data):
        previous_status = instance.teaching_status
        with transaction.atomic():
            updated = super().update(instance, validated_data)
            if previous_status == TeacherProfile.TeachingStatus.ACTIVE and updated.teaching_status == TeacherProfile.TeachingStatus.INACTIVE:
                today = timezone.localdate()
                for assignment in updated.assignments.filter(status=TeacherAssignment.Status.ACTIVE).select_related("academic_session"):
                    assignment.status = TeacherAssignment.Status.ENDED if today >= assignment.start_date else TeacherAssignment.Status.CANCELLED
                    assignment.end_date = min(today, assignment.academic_session.end_date)
                    if assignment.end_date < assignment.start_date:
                        assignment.end_date = assignment.start_date
                    assignment.save()
        return updated


class AssignmentSerializer(SafeStaffSerializer):
    school = serializers.IntegerField(source="school_id", read_only=True)
    teacher = serializers.PrimaryKeyRelatedField(queryset=TeacherProfile.objects.none())
    teacher_name = serializers.SerializerMethodField()
    staff_number = serializers.CharField(source="teacher.staff.staff_number", read_only=True)
    academic_session_name = serializers.CharField(source="academic_session.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    class_arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    previous_assignment_id = serializers.IntegerField(read_only=True)
    reason = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=300)
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())

    class Meta:
        model = TeacherAssignment
        fields = (
            "id", "school", "teacher", "teacher_name", "staff_number", "academic_session", "academic_session_name",
            "class_level", "class_name", "class_arm", "class_arm_name", "subject", "subject_name", "start_date",
            "end_date", "status", "previous_assignment", "previous_assignment_id", "change_reason", "reason", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "teacher_name", "staff_number", "academic_session_name", "class_name", "class_arm_name", "subject_name", "previous_assignment", "previous_assignment_id", "change_reason", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        if school:
            self.fields["teacher"].queryset = TeacherProfile.objects.filter(school=school, teaching_status=TeacherProfile.TeachingStatus.ACTIVE, staff__status=StaffProfile.Status.ACTIVE)
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school).exclude(status=AcademicSession.Status.COMPLETED)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school, is_active=True)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school, is_active=True)
            self.fields["subject"].queryset = Subject.objects.filter(school=school, is_active=True)

    def get_teacher_name(self, obj):
        return f"{obj.teacher.staff.first_name} {obj.teacher.staff.last_name}"

    def validate(self, attrs):
        class_level = attrs.get("class_level", getattr(self.instance, "class_level", None))
        class_arm = attrs.get("class_arm", getattr(self.instance, "class_arm", None))
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        if class_level and class_arm and class_arm.class_level_id != class_level.pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if class_level and subject and ClassSubject.objects.filter(class_level=class_level, is_active=True).exists() and not ClassSubject.objects.filter(class_level=class_level, subject=subject, is_active=True).exists():
            raise serializers.ValidationError({"subject": "Choose a subject assigned to the selected class."})
        if self.instance and any(key in attrs for key in ("teacher", "academic_session", "class_level", "class_arm", "subject", "start_date")):
            raise serializers.ValidationError("Assignment details are immutable; use the replacement workflow.")
        return attrs

    def create(self, validated_data):
        validated_data.pop("reason", None)
        validated_data["school_id"] = self.context["school"].pk
        return super().create(validated_data)


class AssignmentTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(TeacherAssignment.Status.ENDED, TeacherAssignment.Status.CANCELLED))
    end_date = serializers.DateField()


class AssignmentReplacementSerializer(AssignmentSerializer):
    reason = serializers.CharField(max_length=300, write_only=True, required=False, allow_blank=True)

