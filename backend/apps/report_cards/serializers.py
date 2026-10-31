from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term

from .models import ReportCard, ReportCardAuditEvent, ReportCardRevision


class ReportCardRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCardRevision
        fields = ("id", "revision_number", "status", "snapshot", "validation_errors", "reason", "generated_by", "reviewed_by", "approved_by", "finalized_by", "created_at", "reviewed_at", "approved_at", "finalized_at")


class ReportCardAuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportCardAuditEvent
        fields = ("id", "revision", "action", "reason", "metadata", "actor", "actor_name", "created_at")

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.get_username()


class ReportCardSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    current = serializers.SerializerMethodField()
    revisions = ReportCardRevisionSerializer(many=True, read_only=True)
    audit_events = ReportCardAuditSerializer(many=True, read_only=True)

    class Meta:
        model = ReportCard
        fields = ("id", "identifier", "school", "student", "student_name", "admission_number", "enrollment", "academic_session", "session_name", "term", "term_name", "class_level", "class_name", "class_arm", "arm_name", "status", "current_revision", "created_by", "reviewed_by", "approved_by", "finalized_by", "created_at", "updated_at", "reviewed_at", "approved_at", "finalized_at", "current", "revisions", "audit_events")
        read_only_fields = fields

    def get_student_name(self, obj):
        return " ".join(part for part in (obj.student.first_name, obj.student.middle_name, obj.student.last_name) if part)

    def get_current(self, obj):
        revision = obj.revisions.filter(revision_number=obj.current_revision).first()
        return ReportCardRevisionSerializer(revision).data if revision else None


class ReportCardListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    arm_name = serializers.CharField(source="class_arm.name", read_only=True)
    validation_errors = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields = ("id", "identifier", "student", "student_name", "admission_number", "enrollment", "academic_session", "session_name", "term", "term_name", "class_level", "class_name", "class_arm", "arm_name", "status", "current_revision", "updated_at", "validation_errors")

    def get_student_name(self, obj):
        return " ".join(part for part in (obj.student.first_name, obj.student.middle_name, obj.student.last_name) if part)

    def get_validation_errors(self, obj):
        revision = obj.revisions.filter(revision_number=obj.current_revision).first()
        return revision.validation_errors if revision else []


class ReportCardFilterSerializer(serializers.Serializer):
    academic_session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.none(), required=False)
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.none(), required=False)
    class_level = serializers.PrimaryKeyRelatedField(queryset=ClassLevel.objects.none(), required=False)
    class_arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none(), required=False)
    status = serializers.ChoiceField(choices=ReportCard.Status.choices, required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context.get("school")
        if school:
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(school=school)
            self.fields["term"].queryset = Term.objects.filter(school=school)
            self.fields["class_level"].queryset = ClassLevel.objects.filter(school=school)
            self.fields["class_arm"].queryset = ClassArm.objects.filter(school=school)

    def validate(self, attrs):
        if attrs.get("term") and attrs.get("academic_session") and attrs["term"].academic_session_id != attrs["academic_session"].pk:
            raise serializers.ValidationError({"term": "The term must belong to the selected session."})
        if attrs.get("class_arm") and attrs.get("class_level") and attrs["class_arm"].class_level_id != attrs["class_level"].pk:
            raise serializers.ValidationError({"class_arm": "The arm must belong to the selected class."})
        return attrs


class GenerateReportCardSerializer(serializers.Serializer):
    enrollment = serializers.IntegerField(min_value=1)
    term = serializers.IntegerField(min_value=1)


class GenerateClassReportCardsSerializer(serializers.Serializer):
    academic_session = serializers.IntegerField(min_value=1)
    term = serializers.IntegerField(min_value=1)
    class_level = serializers.IntegerField(min_value=1)
    class_arm = serializers.IntegerField(min_value=1)


class ReportCardActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ReportCardRemarksSerializer(serializers.Serializer):
    teacher = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    head_teacher = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    conduct = serializers.CharField(required=False, allow_blank=True, max_length=300)
    effort = serializers.CharField(required=False, allow_blank=True, max_length=300)
    class_teacher_signature_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    head_teacher_signature_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
