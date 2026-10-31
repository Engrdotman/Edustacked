from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.models import School
from apps.students.models import StudentEnrollment

from .models import AttendanceAuditEvent, AttendanceRecord, AttendanceRegister
from .services import eligible_enrollments, local_school_date


class SafeAttendanceSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This attendance record conflicts with an existing register.") from exc


class AttendanceRegisterCreateSerializer(serializers.ModelSerializer):
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.none())
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())

    class Meta:
        model = AttendanceRegister
        fields = ("academic_session", "term", "class_level", "class_arm", "attendance_date")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        if school:
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["term"].queryset = Term.objects.filter(school=school)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school)

    def validate(self, attrs):
        if attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if attrs["term"].academic_session_id != attrs["academic_session"].pk:
            raise serializers.ValidationError({"term": "The selected term does not belong to the selected session."})
        if attrs["attendance_date"] > local_school_date(self.context["school"]):
            raise serializers.ValidationError({"attendance_date": "Future attendance registers are not allowed."})
        if not eligible_enrollments(
            self.context["school"], attrs["academic_session"], attrs["class_level"],
            attrs["class_arm"], attrs["attendance_date"],
        ).exists():
            raise serializers.ValidationError({"class_arm": "There are no eligible students for this class, arm, and date."})
        return attrs

    def create(self, validated_data):
        school = self.context["school"]
        actor = self.context["request"].user
        try:
            with transaction.atomic():
                register = AttendanceRegister.objects.create(school=school, created_by=actor, **validated_data)
                enrollments = eligible_enrollments(school, register.academic_session, register.class_level, register.class_arm, register.attendance_date).select_related("student")
                AttendanceRecord.objects.bulk_create([
                    AttendanceRecord(school=school, register=register, student=enrollment.student, enrollment=enrollment)
                    for enrollment in enrollments
                ])
                return register
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError({"attendance_date": "A register already exists for this class, arm, and date."}) from exc


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    first_name = serializers.CharField(source="student.first_name", read_only=True)
    middle_name = serializers.CharField(source="student.middle_name", read_only=True)
    last_name = serializers.CharField(source="student.last_name", read_only=True)
    enrollment_id = serializers.IntegerField(read_only=True)
    register_version = serializers.IntegerField(source="register.version", read_only=True)
    attendance_date = serializers.DateField(source="register.attendance_date", read_only=True)
    register_status = serializers.CharField(source="register.status", read_only=True)
    class_name = serializers.CharField(source="register.class_level.name", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = ("id", "student", "student_name", "first_name", "middle_name", "last_name", "admission_number", "enrollment_id", "register_version", "attendance_date", "register_status", "class_name", "status", "note", "recorded_by", "last_modified_by", "created_at", "updated_at")
        read_only_fields = fields

    def get_student_name(self, obj):
        return " ".join(part for part in (obj.student.first_name, obj.student.middle_name, obj.student.last_name) if part)


class AttendanceAuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceAuditEvent
        fields = ("id", "event_type", "previous_status", "new_status", "reason", "actor", "actor_name", "created_at")
        read_only_fields = fields

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.get_username()


class AttendanceRegisterSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    records = AttendanceRecordSerializer(many=True, read_only=True)
    audit_events = AttendanceAuditSerializer(many=True, read_only=True)
    total_students = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRegister
        fields = (
            "id", "school", "academic_session", "session_name", "term", "term_name", "class_level", "class_name",
            "class_arm", "arm_name", "attendance_date", "status", "version", "total_students", "created_by",
            "submitted_by", "finalized_by", "reopened_by", "records", "audit_events", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_total_students(self, obj):
        return obj.records.count()


class AttendanceRegisterListSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    total_students = serializers.IntegerField(source="record_count", read_only=True)

    class Meta:
        model = AttendanceRegister
        fields = ("id", "academic_session", "session_name", "term", "term_name", "class_level", "class_name", "class_arm", "arm_name", "attendance_date", "status", "version", "total_students", "created_by", "created_at", "updated_at")
        read_only_fields = fields


class EligibleStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="student_id")
    admission_number = serializers.CharField(source="student.admission_number")
    first_name = serializers.CharField(source="student.first_name")
    middle_name = serializers.CharField(source="student.middle_name")
    last_name = serializers.CharField(source="student.last_name")
    enrollment_id = serializers.IntegerField(source="id")


class BulkAttendanceEntrySerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class BulkAttendanceSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    records = BulkAttendanceEntrySerializer(many=True, allow_empty=False)

    def validate_records(self, records):
        ids = [row["student_id"] for row in records]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("A student may appear only once in a bulk request.")
        return records


class AttendanceRecordUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class RegisterActionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
