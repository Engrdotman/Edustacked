from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel
from apps.schools.tenancy import resolve_authorized_school

from .models import (
    MAX_STUDENT_PHOTO_SIZE, Guardian, Student, StudentEnrollment,
    StudentGuardian,
)


class SafeModelSerializer(serializers.ModelSerializer):
    def _save_model(self, operation):
        try:
            with transaction.atomic():
                return operation()
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This record conflicts with existing school data.") from exc

    def create(self, validated_data):
        return self._save_model(lambda: super(SafeModelSerializer, self).create(validated_data))

    def update(self, instance, validated_data):
        return self._save_model(lambda: super(SafeModelSerializer, self).update(instance, validated_data))


def school_from_context(context):
    school = context.get("school")
    if school:
        return school
    request = context["request"]
    return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))


class StudentRosterSerializer(serializers.ModelSerializer):
    current_class = serializers.SerializerMethodField()
    current_arm = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ("id", "admission_number", "first_name", "middle_name", "last_name", "status", "current_class", "current_arm")
        read_only_fields = fields

    def _current(self, obj):
        return obj.enrollments.filter(status=StudentEnrollment.Status.ACTIVE).select_related("class_level", "class_arm").first()

    def get_current_class(self, obj):
        enrollment = self._current(obj)
        return enrollment.class_level.name if enrollment else None

    def get_current_arm(self, obj):
        enrollment = self._current(obj)
        return enrollment.class_arm.name if enrollment else None


class StudentContactSerializer(StudentRosterSerializer):
    class Meta(StudentRosterSerializer.Meta):
        fields = StudentRosterSerializer.Meta.fields + ("email", "phone", "admission_date")


class StudentManageSerializer(SafeModelSerializer):
    school = serializers.IntegerField(source="school_id", read_only=True)
    photo_present = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id", "school", "admission_number", "first_name", "middle_name", "last_name",
            "date_of_birth", "gender", "photo_present", "email", "phone", "address",
            "admission_date", "status", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "admission_number", "photo_present", "created_at", "updated_at")

    def get_photo_present(self, obj):
        return bool(obj.photo)


class StudentCreateSerializer(StudentManageSerializer):
    admission_number = serializers.CharField(max_length=50)

    class Meta(StudentManageSerializer.Meta):
        read_only_fields = ("id", "school", "photo_present", "created_at", "updated_at")

    def validate_admission_number(self, value):
        value = value.strip()
        school = school_from_context(self.context)
        if Student.objects.filter(school=school, admission_number__iexact=value).exists():
            raise serializers.ValidationError("This admission number is already used at this school.")
        return value

    def to_representation(self, instance):
        request = self.context.get("request")
        role = "school_admin"
        if request and not request.user.is_superuser:
            from apps.schools.permissions import authorized_membership
            role = authorized_membership(request.user, request, self.context.get("view")).role
        serializer = StudentContactSerializer if role == "receptionist" else StudentManageSerializer
        return serializer(instance, context=self.context).data


class GuardianSerializer(SafeModelSerializer):
    school = serializers.IntegerField(source="school_id", read_only=True)

    class Meta:
        model = Guardian
        fields = ("id", "school", "full_name", "phone", "email", "address", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "created_at", "updated_at")


class GuardianAdmissionSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    relationship_type = serializers.CharField(max_length=40)
    is_primary_contact = serializers.BooleanField(default=False)
    is_emergency_contact = serializers.BooleanField(default=False)
    can_receive_communications = serializers.BooleanField(default=True)


class EnrollmentInputSerializer(serializers.Serializer):
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    enrollment_date = serializers.DateField(required=False)
    status = serializers.ChoiceField(choices=StudentEnrollment.Status.choices, default=StudentEnrollment.Status.PENDING)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            school = school_from_context(self.context)
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school)

    def validate(self, attrs):
        if attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if not attrs["class_level"].is_active or not attrs["class_arm"].is_active:
            raise serializers.ValidationError("Select an active class and class arm.")
        return attrs


class StudentAdmissionSerializer(serializers.Serializer):
    student = StudentCreateSerializer()
    guardians = GuardianAdmissionSerializer(many=True, required=False)
    enrollment = EnrollmentInputSerializer(required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            school = school_from_context(self.context)
            self.fields["enrollment"].fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["enrollment"].fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["enrollment"].fields["class_arm"].queryset = ClassArm.objects.filter(school=school)

    def validate(self, attrs):
        primary_count = sum(1 for guardian in attrs.get("guardians", []) if guardian["is_primary_contact"])
        if primary_count > 1:
            raise serializers.ValidationError({"guardians": "Only one guardian may be the primary contact for a student."})
        if attrs.get("student", {}).get("status", Student.Status.ACTIVE) != Student.Status.ACTIVE and attrs.get("enrollment"):
            raise serializers.ValidationError({"enrollment": "An inactive student cannot be enrolled."})
        return attrs

    def create(self, validated_data):
        school = school_from_context(self.context)
        student_data = validated_data["student"]
        guardians_data = validated_data.get("guardians", [])
        enrollment_data = validated_data.get("enrollment")
        try:
            with transaction.atomic():
                student = Student.objects.create(school=school, **student_data)
                for guardian_data in guardians_data:
                    relationship_type = guardian_data.pop("relationship_type")
                    guardian = Guardian.objects.create(school=school, **{
                        key: value for key, value in guardian_data.items()
                        if key in {"full_name", "phone", "email", "address"}
                    })
                    StudentGuardian.objects.create(
                        school=school,
                        student=student,
                        guardian=guardian,
                        relationship_type=relationship_type,
                        **{key: value for key, value in guardian_data.items() if key in {
                            "is_primary_contact", "is_emergency_contact", "can_receive_communications"
                        }},
                    )
                if enrollment_data:
                    session = enrollment_data.pop("academic_session")
                    class_level = enrollment_data.pop("class_level")
                    class_arm = enrollment_data.pop("class_arm")
                    StudentEnrollment.objects.create(
                        school=school,
                        student=student,
                        academic_session=session,
                        class_level=class_level,
                        class_arm=class_arm,
                        **enrollment_data,
                    )
                return student
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("Admission conflicts with existing school records.") from exc

    def to_representation(self, instance):
        role = "school_admin"
        user = self.context.get("request").user if self.context.get("request") else None
        if user and not user.is_superuser:
            from apps.schools.permissions import authorized_membership
            role = authorized_membership(user, self.context["request"], self.context.get("view")).role
        serializer = StudentRosterSerializer if role == "teacher" else StudentContactSerializer if role == "receptionist" else StudentManageSerializer
        return serializer(instance, context=self.context).data


class StudentGuardianReadSerializer(serializers.ModelSerializer):
    guardian_id = serializers.IntegerField(source="guardian_id", read_only=True)
    full_name = serializers.CharField(source="guardian.full_name", read_only=True)
    phone = serializers.CharField(source="guardian.phone", read_only=True)
    email = serializers.EmailField(source="guardian.email", read_only=True)
    address = serializers.CharField(source="guardian.address", read_only=True)

    class Meta:
        model = StudentGuardian
        fields = (
            "id", "guardian_id", "full_name", "phone", "email", "address", "relationship_type",
            "is_primary_contact", "is_emergency_contact", "can_receive_communications", "is_active",
        )
        read_only_fields = fields


class StudentGuardianCreateSerializer(serializers.Serializer):
    guardian_id = serializers.IntegerField(required=False)
    full_name = serializers.CharField(max_length=200, required=False)
    phone = serializers.CharField(max_length=30, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    relationship_type = serializers.CharField(max_length=40)
    is_primary_contact = serializers.BooleanField(default=False)
    is_emergency_contact = serializers.BooleanField(default=False)
    can_receive_communications = serializers.BooleanField(default=True)

    def validate(self, attrs):
        school = school_from_context(self.context)
        guardian_id = attrs.get("guardian_id")
        if guardian_id:
            guardian = Guardian.objects.filter(school=school, pk=guardian_id, is_active=True).first()
            if not guardian:
                raise serializers.ValidationError({"guardian_id": "Choose an active guardian in this school."})
            attrs["guardian"] = guardian
            if any(key in attrs for key in ("full_name", "phone", "email", "address")):
                raise serializers.ValidationError("When linking an existing guardian, omit guardian contact fields.")
        elif not attrs.get("full_name") or not attrs.get("phone"):
            raise serializers.ValidationError({"full_name": "Provide a guardian name and phone, or choose an existing guardian."})
        return attrs

    def create(self, validated_data):
        school = school_from_context(self.context)
        student = self.context["student"]
        guardian = validated_data.pop("guardian", None)
        try:
            with transaction.atomic():
                if guardian is None:
                    guardian_data = {key: validated_data.pop(key, "") for key in ("full_name", "phone", "email", "address")}
                    guardian = Guardian.objects.create(school=school, **guardian_data)
                validated_data.pop("guardian_id", None)
                return StudentGuardian.objects.create(
                    school=school, student=student, guardian=guardian, **validated_data
                )
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This guardian is already linked or conflicts with a primary contact.") from exc


class StudentGuardianUpdateSerializer(SafeModelSerializer):
    class Meta:
        model = StudentGuardian
        fields = ("relationship_type", "is_primary_contact", "is_emergency_contact", "can_receive_communications", "is_active")


class EnrollmentReadSerializer(serializers.ModelSerializer):
    academic_session_name = serializers.CharField(source="academic_session.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    class_arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    previous_enrollment_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudentEnrollment
        fields = (
            "id", "student", "academic_session", "academic_session_name", "class_level", "class_name",
            "class_arm", "class_arm_name", "enrollment_date", "status", "withdrawal_date",
            "withdrawal_reason", "transfer_date", "transfer_reason", "previous_enrollment_id", "created_at",
        )
        read_only_fields = fields


class EnrollmentCreateSerializer(SafeModelSerializer):
    school = serializers.IntegerField(read_only=True)
    student = serializers.IntegerField(read_only=True)
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    withdrawal_date = serializers.DateField(required=False, allow_null=True)
    withdrawal_reason = serializers.CharField(required=False, allow_blank=True, max_length=300)

    class Meta:
        model = StudentEnrollment
        fields = (
            "id", "school", "student", "academic_session", "class_level", "class_arm", "enrollment_date",
            "status", "withdrawal_date", "withdrawal_reason", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "student", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            school = school_from_context(self.context)
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school)

    def validate(self, attrs):
        if attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        return attrs

    def create(self, validated_data):
        student = self.context["student"]
        school = school_from_context(self.context)
        try:
            with transaction.atomic():
                Student.objects.select_for_update().get(pk=student.pk)
                AcademicSession.objects.select_for_update().get(pk=validated_data["academic_session"].pk)
                return super().create({**validated_data, "school": school, "student": student})
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This student already has an enrollment for the selected session.") from exc

    def to_representation(self, instance):
        return EnrollmentReadSerializer(instance, context=self.context).data


class EnrollmentTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED, StudentEnrollment.Status.WITHDRAWN))
    withdrawal_date = serializers.DateField(required=False, allow_null=True)
    withdrawal_reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class EnrollmentTransferSerializer(serializers.Serializer):
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    transfer_date = serializers.DateField()
    reason = serializers.CharField(max_length=300)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            school = school_from_context(self.context)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school, is_active=True)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school, is_active=True)

    def validate(self, attrs):
        if attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        return attrs


class StudentPhotoSerializer(serializers.Serializer):
    photo = serializers.ImageField()

    def validate_photo(self, value):
        if value.size > MAX_STUDENT_PHOTO_SIZE:
            raise serializers.ValidationError("Student photos must be 2 MB or smaller.")
        image_format = getattr(value.image, "format", "").upper()
        extension = value.name.rsplit(".", 1)[-1].lower()
        expected = {"jpeg": {"jpeg", "jpg"}, "png": {"png"}, "webp": {"webp"}}
        if image_format.lower() not in expected or extension not in expected[image_format.lower()]:
            raise serializers.ValidationError("Use a JPG, PNG, or WebP image.")
        return value
