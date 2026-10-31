from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, GradingScale, Subject, Term
from apps.schools.models import School
from .models import AssessmentComponent, AssessmentPlan, AssessmentResult, ComponentScore, PlanComponent, ResultAuditEvent
from .services import grading_snapshot


class SafeModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This assessment configuration conflicts with an existing record.") from exc

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("This assessment configuration conflicts with an existing record.") from exc


class AssessmentComponentSerializer(SafeModelSerializer):
    class Meta:
        model = AssessmentComponent
        fields = ("id", "name", "max_score", "default_weight", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        school = self.context["school"]
        name = attrs.get("name", getattr(self.instance, "name", "")).strip()
        qs = AssessmentComponent.objects.filter(school=school, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": "A component with this name already exists in this school."})
        return attrs

    def create(self, validated_data):
        return super().create({**validated_data, "school": self.context["school"]})


class PlanComponentSerializer(SafeModelSerializer):
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = PlanComponent
        fields = ("id", "component", "component_name", "max_score", "weight", "position", "created_at")
        read_only_fields = ("id", "component_name", "created_at")

    def validate_component(self, value):
        if value.school_id != self.context["school"].pk or not value.is_active:
            raise serializers.ValidationError("Choose an active component from this school.")
        return value

    def validate(self, attrs):
        plan = self.context["plan"]
        component = attrs.get("component", getattr(self.instance, "component", None))
        if component and PlanComponent.objects.filter(plan=plan, component=component).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({"component": "This component is already on the plan."})
        return attrs


class AssessmentPlanSerializer(SafeModelSerializer):
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none())
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.none())
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none())
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())
    grading_scale = serializers.PrimaryKeyRelatedField(queryset=GradingScale.objects.none())
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    grading_scale_name = serializers.CharField(source="grading_scale.name", read_only=True)
    components = PlanComponentSerializer(many=True, read_only=True)
    result_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AssessmentPlan
        fields = ("id", "academic_session", "session_name", "term", "term_name", "class_level", "class_name", "class_arm", "arm_name", "subject", "subject_name", "grading_scale", "grading_scale_name", "name", "calculation_method", "grading_scale_snapshot", "status", "version", "components", "result_count", "created_by", "published_by", "closed_by", "reopened_by", "created_at", "updated_at")
        read_only_fields = ("id", "grading_scale_snapshot", "status", "version", "components", "result_count", "created_by", "published_by", "closed_by", "reopened_by", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        if school:
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["term"].queryset = Term.objects.filter(school=school)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school)
            self.fields["subject"].queryset = Subject.objects.filter(school=school)
            self.fields["grading_scale"].queryset = GradingScale.objects.filter(school=school, is_active=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            if self.instance.status != AssessmentPlan.Status.DRAFT:
                raise serializers.ValidationError("Only draft assessment plans can be edited.")
            if self.instance.results.filter(scores__isnull=False).exists():
                changed = any(getattr(self.instance, key) != val for key, val in attrs.items() if key in {"academic_session", "term", "class_level", "class_arm", "subject", "grading_scale", "name", "calculation_method"})
                if changed:
                    raise serializers.ValidationError("Plan configuration is locked after score entry begins.")
        school = self.context["school"]
        if not self.instance and attrs.get("term") and attrs.get("academic_session") and attrs["term"].academic_session_id != attrs["academic_session"].pk:
            raise serializers.ValidationError({"term": "The term must belong to the selected session."})
        if attrs.get("class_arm") and attrs.get("class_level") and attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The arm must belong to the selected class."})
        if attrs.get("class_level") and attrs.get("subject"):
            from apps.academics.models import ClassSubject
            configured = ClassSubject.objects.filter(school=school, class_level=attrs["class_level"], is_active=True)
            if configured.exists() and not configured.filter(subject=attrs["subject"]).exists():
                raise serializers.ValidationError({"subject": "This subject is not assigned to the selected class."})
        return attrs

    def create(self, validated_data):
        validated_data.update(school=self.context["school"], created_by=self.context["request"].user, grading_scale_snapshot=grading_snapshot(validated_data["grading_scale"]))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "grading_scale" in validated_data:
            validated_data["grading_scale_snapshot"] = grading_snapshot(validated_data["grading_scale"])
        return super().update(instance, validated_data)


class ComponentScoreSerializer(serializers.ModelSerializer):
    plan_component_id = serializers.IntegerField(source="plan_component.id", read_only=True)
    component_name = serializers.CharField(source="plan_component.component.name", read_only=True)
    max_score = serializers.DecimalField(source="plan_component.max_score", max_digits=7, decimal_places=2, read_only=True)

    class Meta:
        model = ComponentScore
        fields = ("id", "plan_component_id", "component_name", "score", "max_score", "recorded_by", "last_modified_by", "created_at", "updated_at")
        read_only_fields = fields


class ResultAuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ResultAuditEvent
        fields = ("id", "event_type", "previous_value", "new_value", "reason", "actor", "actor_name", "created_at")

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.get_username()


class AssessmentResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    scores = ComponentScoreSerializer(many=True, read_only=True)
    audit_events = ResultAuditSerializer(many=True, read_only=True)
    calculation = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentResult
        fields = ("id", "student", "student_name", "admission_number", "enrollment", "status", "version", "scores", "calculation", "approved_total", "approved_maximum", "approved_percentage", "approved_grade", "approved_grade_point", "submitted_by", "approved_by", "reopened_by", "audit_events", "created_at", "updated_at")
        read_only_fields = fields

    def get_student_name(self, obj):
        return " ".join(part for part in (obj.student.first_name, obj.student.middle_name, obj.student.last_name) if part)

    def get_calculation(self, obj):
        from .services import calculate_result
        if obj.status == AssessmentResult.Status.APPROVED and obj.approved_calculation:
            return obj.approved_calculation
        return calculate_result(obj)


class ScoreValueSerializer(serializers.Serializer):
    plan_component_id = serializers.IntegerField(min_value=1)
    score = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0)


class StudentScoreEntrySerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    version = serializers.IntegerField(min_value=0)
    scores = ScoreValueSerializer(many=True, allow_empty=False)

    def validate_scores(self, values):
        ids = [row["plan_component_id"] for row in values]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("A plan component may appear only once per student.")
        return values


class BulkScoreSerializer(serializers.Serializer):
    entries = StudentScoreEntrySerializer(many=True, allow_empty=False)

    def validate_entries(self, entries):
        ids = [row["student_id"] for row in entries]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("A student may appear only once in a bulk request.")
        return entries


class ResultBatchActionSerializer(serializers.Serializer):
    entries = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_entries(self, entries):
        student_ids = []
        for entry in entries:
            if set(entry) != {"student_id", "version"} or not str(entry["student_id"]).isdecimal() or not str(entry["version"]).isdecimal():
                raise serializers.ValidationError("Each entry requires integer student_id and version values.")
            student_ids.append(int(entry["student_id"]))
        if len(student_ids) != len(set(student_ids)):
            raise serializers.ValidationError("A student may appear only once in a batch.")
        return [{"student_id": int(row["student_id"]), "version": int(row["version"])} for row in entries]
