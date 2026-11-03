import json

from django.utils import timezone
from rest_framework import serializers

from apps.academics.models import AcademicSession, ClassLevel, Subject, Term
from apps.students.models import Student

from .models import Examination, ExaminationAssignment, ExaminationQuestion, Question, QuestionOption


class QuestionOptionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)

    class Meta:
        model = QuestionOption
        fields = ("id", "text", "position", "is_correct")
        extra_kwargs = {"text": {"trim_whitespace": True}}


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = (
            "id", "subject", "subject_name", "class_level", "class_name", "topic", "text",
            "question_type", "difficulty", "marks", "explanation", "image", "status", "options",
            "created_by", "created_by_name", "created_at", "updated_at",
        )
        read_only_fields = ("id", "status", "created_by", "created_by_name", "created_at", "updated_at")

    def to_internal_value(self, data):
        if hasattr(data, "get") and isinstance(data.get("options"), str):
            data = data.copy()
            try:
                data["options"] = json.loads(data["options"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise serializers.ValidationError({"options": "Provide answer options as a JSON list."}) from exc
        return super().to_internal_value(data)

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() or obj.created_by.email

    def validate(self, attrs):
        school = self.context["school"]
        subject = attrs.get("subject", self.instance.subject if self.instance else None)
        class_level = attrs.get("class_level", self.instance.class_level if self.instance else None)
        if subject and subject.school_id != school.pk:
            raise serializers.ValidationError({"subject": "Choose a subject belonging to this school."})
        if class_level and class_level.school_id != school.pk:
            raise serializers.ValidationError({"class_level": "Choose a class belonging to this school."})

        question_type = attrs.get("question_type", self.instance.question_type if self.instance else None)
        options = attrs.get("options")
        if options is None and self.instance:
            options = list(self.instance.options.values("text", "is_correct"))
        options = options or []
        if question_type == Question.Type.TEXT:
            if options:
                raise serializers.ValidationError({"options": "Text response questions cannot have answer options."})
        else:
            if len(options) < 2:
                raise serializers.ValidationError({"options": "Multiple-choice questions require at least two options."})
            normalized_text = [option["text"].strip().casefold() for option in options]
            if any(not value for value in normalized_text) or len(normalized_text) != len(set(normalized_text)):
                raise serializers.ValidationError({"options": "Answer options must be non-empty and unique."})
            correct_count = sum(bool(option.get("is_correct")) for option in options)
            if question_type == Question.Type.SINGLE_CHOICE and correct_count != 1:
                raise serializers.ValidationError({"options": "Select exactly one correct option."})
            if question_type == Question.Type.MULTIPLE_ANSWER and correct_count < 1:
                raise serializers.ValidationError({"options": "Select at least one correct option."})
        return attrs

    def create(self, validated_data):
        options = validated_data.pop("options", [])
        question = Question.objects.create(
            school=self.context["school"], created_by=self.context["request"].user, **validated_data
        )
        self._save_options(question, options)
        return question

    def update(self, instance, validated_data):
        options = validated_data.pop("options", serializers.empty)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        if options is not serializers.empty:
            self._save_options(instance, options)
        elif instance.question_type == Question.Type.TEXT:
            instance.options.all().delete()
        return instance

    @staticmethod
    def _save_options(question, options):
        question.options.all().delete()
        QuestionOption.objects.bulk_create([
            QuestionOption(question=question, text=option["text"].strip(), position=position, is_correct=option.get("is_correct", False))
            for position, option in enumerate(options)
        ])


class ExaminationQuestionSerializer(serializers.ModelSerializer):
    source_question_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ExaminationQuestion
        fields = ("id", "source_question_id", "position", "prompt_snapshot", "type_snapshot", "marks_snapshot", "is_snapshot")


class ExaminationSerializer(serializers.ModelSerializer):
    question_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    selected_questions = ExaminationQuestionSerializer(source="exam_questions", many=True, read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(source="class_level.name", read_only=True)
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True, default="")

    class Meta:
        model = Examination
        fields = (
            "id", "title", "description", "instructions", "subject", "subject_name", "class_level", "class_name",
            "academic_session", "session_name", "term", "term_name", "duration_minutes", "starts_at", "ends_at",
            "total_marks", "pass_mark", "status", "randomize_question_order", "randomize_answer_options",
            "maximum_attempts", "selection_method", "random_question_count", "question_criteria", "question_ids",
            "selected_questions", "created_by", "published_at", "created_at", "updated_at",
        )
        read_only_fields = ("id", "total_marks", "status", "selected_questions", "created_by", "published_at", "created_at", "updated_at")

    def validate(self, attrs):
        school = self.context["school"]
        related = {
            "subject": attrs.get("subject", self.instance.subject if self.instance else None),
            "class_level": attrs.get("class_level", self.instance.class_level if self.instance else None),
            "academic_session": attrs.get("academic_session", self.instance.academic_session if self.instance else None),
            "term": attrs.get("term", self.instance.term if self.instance else None),
        }
        for field, value in related.items():
            if value and value.school_id != school.pk:
                raise serializers.ValidationError({field: f"Choose a {field.replace('_', ' ')} belonging to this school."})
        session = related["academic_session"]
        term = related["term"]
        if term and session and term.academic_session_id != session.pk:
            raise serializers.ValidationError({"term": "Choose a term from the selected academic session."})
        starts_at = attrs.get("starts_at", self.instance.starts_at if self.instance else None)
        ends_at = attrs.get("ends_at", self.instance.ends_at if self.instance else None)
        if starts_at and ends_at:
            if ends_at <= starts_at:
                raise serializers.ValidationError({"ends_at": "End time must be after start time."})
            start_date = timezone.localtime(starts_at).date()
            end_date = timezone.localtime(ends_at).date()
            if session and (start_date < session.start_date or end_date > session.end_date):
                raise serializers.ValidationError({"starts_at": "The schedule must fall within the academic session."})
            if term and (start_date < term.start_date or end_date > term.end_date):
                raise serializers.ValidationError({"starts_at": "The schedule must fall within the selected term."})
        pass_mark = attrs.get("pass_mark", self.instance.pass_mark if self.instance else None)
        if pass_mark is not None and pass_mark < 0:
            raise serializers.ValidationError({"pass_mark": "Pass mark cannot be negative."})
        method = attrs.get("selection_method", self.instance.selection_method if self.instance else Examination.SelectionMethod.MANUAL)
        random_count = attrs.get("random_question_count", self.instance.random_question_count if self.instance else None)
        if method == Examination.SelectionMethod.RANDOM and (not random_count or random_count < 1):
            raise serializers.ValidationError({"random_question_count": "Choose a positive question count for random selection."})
        if method == Examination.SelectionMethod.MANUAL and random_count:
            raise serializers.ValidationError({"random_question_count": "This field is only used for random selection."})
        if "question_criteria" in attrs:
            criteria = attrs["question_criteria"]
            if not isinstance(criteria, dict) or set(criteria) - {"difficulty", "topic"}:
                raise serializers.ValidationError({"question_criteria": "Only difficulty and topic filters are supported."})
            if criteria.get("difficulty") and criteria["difficulty"] not in Question.Difficulty.values:
                raise serializers.ValidationError({"question_criteria": "Choose a valid difficulty."})

        if "question_ids" in attrs:
            question_ids = attrs["question_ids"]
            if len(question_ids) != len(set(question_ids)):
                raise serializers.ValidationError({"question_ids": "A question cannot be selected more than once."})
            if method == Examination.SelectionMethod.MANUAL:
                questions = Question.objects.filter(pk__in=question_ids, school=school)
                if questions.count() != len(question_ids):
                    raise serializers.ValidationError({"question_ids": "One or more questions are unavailable."})
                subject = related["subject"]
                class_level = related["class_level"]
                if any(q.status != Question.Status.PUBLISHED or q.subject_id != subject.pk or q.class_level_id != class_level.pk for q in questions):
                    raise serializers.ValidationError({"question_ids": "Selected questions must be published and match this examination's subject and class."})
            elif question_ids:
                raise serializers.ValidationError({"question_ids": "Select questions manually only for a manual examination."})
        return attrs

    def create(self, validated_data):
        question_ids = validated_data.pop("question_ids", [])
        exam = Examination.objects.create(school=self.context["school"], created_by=self.context["request"].user, **validated_data)
        self._set_manual_questions(exam, question_ids)
        return exam

    def update(self, instance, validated_data):
        question_ids = validated_data.pop("question_ids", serializers.empty)
        if instance.is_frozen:
            raise serializers.ValidationError("Published examinations are locked. Create a new draft for changes.")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        if question_ids is not serializers.empty:
            self._set_manual_questions(instance, question_ids)
        return instance

    @staticmethod
    def _set_manual_questions(examination, question_ids):
        examination.exam_questions.all().delete()
        ExaminationQuestion.objects.bulk_create([
            ExaminationQuestion(examination=examination, source_question_id=question_id, position=position)
            for position, question_id in enumerate(question_ids)
        ])


class AssignmentRequestSerializer(serializers.Serializer):
    all_students = serializers.BooleanField(default=False)
    student_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=True)

    def validate(self, attrs):
        if attrs["all_students"] and attrs.get("student_ids"):
            raise serializers.ValidationError("Choose the whole class or individual students, not both.")
        if not attrs["all_students"] and len(attrs.get("student_ids", [])) != len(set(attrs.get("student_ids", []))):
            raise serializers.ValidationError({"student_ids": "A student can only be selected once."})
        return attrs


class ExaminationAssignmentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)

    class Meta:
        model = ExaminationAssignment
        fields = ("id", "student", "student_name", "admission_number", "status", "assigned_at")

    def get_student_name(self, obj):
        student = obj.student
        return " ".join(part for part in (student.first_name, student.middle_name, student.last_name) if part)


class ExaminationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(
        Examination.Status.ACTIVE,
        Examination.Status.COMPLETED,
        Examination.Status.ARCHIVED,
    ))
