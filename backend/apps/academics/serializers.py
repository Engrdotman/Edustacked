from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.schools.tenancy import resolve_authorized_school

from .models import (
    AcademicSession, ClassArm, ClassLevel, ClassSubject, GradeBand,
    GradingScale, Subject, Term,
)


class ValidatedModelSerializer(serializers.ModelSerializer):
    """Translate model and database integrity failures to consistent API errors."""

    def _save_model(self, operation):
        try:
            with transaction.atomic():
                return operation()
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This record conflicts with existing academic configuration.") from exc

    def create(self, validated_data):
        return self._save_model(lambda: super(ValidatedModelSerializer, self).create(validated_data))

    def update(self, instance, validated_data):
        return self._save_model(lambda: super(ValidatedModelSerializer, self).update(instance, validated_data))


def school_from_context(context):
    school = context.get("school")
    if school:
        return school
    request = context["request"]
    return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))


class AcademicSessionSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AcademicSession
        fields = ("id", "school", "name", "start_date", "end_date", "status", "created_at", "updated_at")
        read_only_fields = ("id", "school", "created_at", "updated_at")


class TermSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    session_name = serializers.CharField(source="academic_session.name", read_only=True)

    class Meta:
        model = Term
        fields = (
            "id", "school", "academic_session", "session_name", "name", "sequence",
            "start_date", "end_date", "status", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "session_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            school = school_from_context(self.context)
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)

    def create(self, validated_data):
        session_id = validated_data["academic_session"].pk
        with transaction.atomic():
            AcademicSession.objects.select_for_update().get(pk=session_id)
            return super().create(validated_data)

    def update(self, instance, validated_data):
        session_ids = {instance.academic_session_id}
        target_session = validated_data.get("academic_session")
        if target_session:
            session_ids.add(target_session.pk)
        with transaction.atomic():
            list(AcademicSession.objects.select_for_update().filter(pk__in=session_ids).order_by("pk"))
            return super().update(instance, validated_data)


class ClassLevelSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ClassLevel
        fields = ("id", "school", "name", "code", "category", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "created_at", "updated_at")


class ClassArmSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    class_level = serializers.PrimaryKeyRelatedField(read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = ClassArm
        fields = ("id", "school", "class_level", "class_name", "name", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "class_level", "class_name", "created_at", "updated_at")


class SubjectSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Subject
        fields = ("id", "school", "name", "code", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "created_at", "updated_at")


class ClassSubjectSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    class_level = serializers.PrimaryKeyRelatedField(read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = ClassSubject
        fields = ("id", "school", "class_level", "class_name", "subject", "subject_name", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "class_level", "class_name", "subject_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            self.fields["subject"].queryset = Subject.objects.filter(school=school_from_context(self.context))


class GradingScaleSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = GradingScale
        fields = ("id", "school", "name", "maximum_score", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "school", "created_at", "updated_at")


class GradeBandSerializer(ValidatedModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    grading_scale = serializers.PrimaryKeyRelatedField(read_only=True)
    scale_name = serializers.CharField(source="grading_scale.name", read_only=True)

    class Meta:
        model = GradeBand
        fields = (
            "id", "school", "grading_scale", "scale_name", "label", "min_score", "max_score",
            "description", "grade_point", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "school", "grading_scale", "scale_name", "created_at", "updated_at")

    def create(self, validated_data):
        scale_id = validated_data["grading_scale"].pk
        with transaction.atomic():
            GradingScale.objects.select_for_update().get(pk=scale_id)
            return super().create(validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            GradingScale.objects.select_for_update().get(pk=instance.grading_scale_id)
            return super().update(instance, validated_data)
