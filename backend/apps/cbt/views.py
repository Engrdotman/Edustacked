from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from rest_framework import generics, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicSession, ClassLevel, Subject, Term
from apps.schools.models import SchoolMembership
from apps.schools.permissions import HasSchoolPermission
from apps.schools.tenancy import resolve_authorized_school
from apps.students.models import Student, StudentEnrollment
from apps.entitlements.permissions import HasActiveServiceEntitlement

from .models import (
    CbtExaminationPackage,
    CbtSyncedSubmission,
    Examination,
    ExaminationAssignment,
    LocalCbtServerCredential,
    LocalCbtSyncEvent,
    Question,
)
from .serializers import (
    AssignmentRequestSerializer,
    ExaminationAssignmentSerializer,
    ExaminationSerializer,
    ExaminationStatusSerializer,
    QuestionSerializer,
)
from .services import (
    assign_examination,
    change_examination_status,
    create_examination_package,
    ingest_local_submission,
    issue_local_server_credential,
    publish_examination,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested change conflicts with existing examination history."
    default_code = "conflict"


class CbtPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CbtSchoolViewMixin:
    required_service_code = "offline_cbt"
    school_permission_by_method = {}

    def get_permissions(self):
        self.required_school_permission = self.school_permission_by_method.get(
            self.request.method,
            self.school_permission_by_method.get("default", getattr(self, "required_school_permission", None)),
        )
        return [IsAuthenticated(), HasSchoolPermission(), HasActiveServiceEntitlement()]

    def get_school(self):
        try:
            return resolve_authorized_school(self.request.user, self.request.headers.get("X-School-ID"))
        except (Http404, ObjectDoesNotExist):
            raise Http404 from None

    @staticmethod
    def raise_validation(error):
        if isinstance(error, DjangoValidationError):
            details = getattr(error, "message_dict", None) or getattr(error, "messages", [str(error)])
            from rest_framework import serializers
            raise serializers.ValidationError(details) from error
        raise error

    def teacher_is_limited(self):
        if self.request.user.is_superuser:
            return False
        membership = SchoolMembership.objects.filter(user=self.request.user, school=self.get_school(), is_active=True).first()
        return bool(membership and membership.role == SchoolMembership.Role.TEACHER)


class QuestionListCreateView(CbtSchoolViewMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    school_permission_by_method = {"GET": "cbt.questions.view", "POST": "cbt.questions.manage"}
    serializer_class = QuestionSerializer
    pagination_class = CbtPagination

    def get_queryset(self):
        school = self.get_school()
        queryset = Question.objects.filter(school=school).select_related("subject", "class_level", "created_by").prefetch_related("options")
        if self.teacher_is_limited():
            queryset = queryset.filter(Q(status=Question.Status.PUBLISHED) | Q(created_by=self.request.user))
        for field in ("subject", "class_level", "status", "difficulty", "question_type"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id" if field in {"subject", "class_level"} else field: value})
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(text__icontains=search) | Q(topic__icontains=search))
        return queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": self.get_school()}


class QuestionDetailView(CbtSchoolViewMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    school_permission_by_method = {"GET": "cbt.questions.view", "HEAD": "cbt.questions.view", "default": "cbt.questions.manage"}
    serializer_class = QuestionSerializer
    lookup_field = "id"

    def get_queryset(self):
        queryset = Question.objects.filter(school=self.get_school()).select_related("subject", "class_level", "created_by").prefetch_related("options")
        if self.teacher_is_limited():
            queryset = queryset.filter(Q(status=Question.Status.PUBLISHED) | Q(created_by=self.request.user))
        return queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": self.get_school()}

    def perform_update(self, serializer):
        if self.teacher_is_limited() and serializer.instance.created_by_id != self.request.user.pk:
            raise PermissionDenied("Teachers can edit only questions they created.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.teacher_is_limited() and instance.created_by_id != self.request.user.pk:
            raise PermissionDenied("Teachers can delete only questions they created.")
        if instance.status != Question.Status.DRAFT:
            raise PermissionDenied("Only unused draft questions can be deleted. Archive published questions instead.")
        try:
            instance.delete()
        except ProtectedError as exc:
            raise Conflict("This question is part of an examination history and cannot be deleted. Archive it instead.") from exc


class QuestionPublishView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.questions.publish"

    def post(self, request, question_id, **kwargs):
        school = self.get_school()
        question = Question.objects.filter(pk=question_id, school=school).prefetch_related("options").first()
        if not question:
            raise Http404
        if self.teacher_is_limited() and question.created_by_id != request.user.pk:
            raise PermissionDenied("Teachers can publish only questions they created.")
        if question.status == Question.Status.ARCHIVED:
            return Response({"detail": "Archived questions cannot be published."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            self.validate_question(question)
        except DjangoValidationError as exc:
            self.raise_validation(exc)
        question.status = Question.Status.PUBLISHED
        question.save(update_fields=("status", "updated_at"))
        return Response(QuestionSerializer(question, context={"school": school}).data)

    @staticmethod
    def validate_question(question):
        options = list(question.options.all())
        if question.question_type == Question.Type.TEXT:
            if options:
                raise DjangoValidationError({"options": "Text response questions cannot have answer options."})
            return
        if len(options) < 2:
            raise DjangoValidationError({"options": "Multiple-choice questions require at least two options."})
        correct_count = sum(option.is_correct for option in options)
        if question.question_type == Question.Type.SINGLE_CHOICE and correct_count != 1:
            raise DjangoValidationError({"options": "A single-choice question must have exactly one correct option."})
        if question.question_type == Question.Type.MULTIPLE_ANSWER and correct_count < 1:
            raise DjangoValidationError({"options": "A multiple-answer question must have at least one correct option."})


class QuestionArchiveView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.questions.manage"

    def post(self, request, question_id, **kwargs):
        question = Question.objects.filter(pk=question_id, school=self.get_school()).first()
        if not question:
            raise Http404
        if self.teacher_is_limited() and question.created_by_id != request.user.pk:
            raise PermissionDenied("Teachers can archive only questions they created.")
        question.status = Question.Status.ARCHIVED
        question.save(update_fields=("status", "updated_at"))
        return Response(QuestionSerializer(question, context={"school": question.school}).data)


class ExaminationListCreateView(CbtSchoolViewMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    school_permission_by_method = {"GET": "cbt.exams.view", "POST": "cbt.exams.manage"}
    serializer_class = ExaminationSerializer
    pagination_class = CbtPagination

    def get_queryset(self):
        queryset = Examination.objects.filter(school=self.get_school()).select_related("subject", "class_level", "academic_session", "term", "created_by").prefetch_related("exam_questions")
        for field in ("subject", "class_level", "academic_session", "status"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id" if field != "status" else field: value})
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))
        return queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": self.get_school()}


class ExaminationDetailView(CbtSchoolViewMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    school_permission_by_method = {"GET": "cbt.exams.view", "HEAD": "cbt.exams.view", "default": "cbt.exams.manage"}
    serializer_class = ExaminationSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Examination.objects.filter(school=self.get_school()).select_related("subject", "class_level", "academic_session", "term").prefetch_related("exam_questions")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "school": self.get_school()}

    def perform_update(self, serializer):
        if serializer.instance.is_frozen:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Published examinations are locked. Create a new draft for changes.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Examination.Status.DRAFT or instance.assignments.exists():
            raise PermissionDenied("Only unassigned draft examinations can be deleted. Archive examinations with history.")
        instance.delete()


class ExaminationPublishView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.exams.publish"

    def post(self, request, examination_id, **kwargs):
        try:
            examination = publish_examination(examination_id, self.get_school(), request.user)
        except (DjangoValidationError, Examination.DoesNotExist) as exc:
            if isinstance(exc, Examination.DoesNotExist):
                raise Http404 from exc
            self.raise_validation(exc)
        return Response(ExaminationSerializer(examination, context={"school": examination.school}).data)


class ExaminationStatusView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.exams.publish"

    def post(self, request, examination_id, **kwargs):
        serializer = ExaminationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            examination = change_examination_status(examination_id, self.get_school(), serializer.validated_data["status"])
        except (DjangoValidationError, Examination.DoesNotExist) as exc:
            if isinstance(exc, Examination.DoesNotExist):
                raise Http404 from exc
            self.raise_validation(exc)
        return Response(ExaminationSerializer(examination, context={"school": examination.school}).data)


class ExaminationAssignmentView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)

    def get_permissions(self):
        self.required_school_permission = "cbt.exams.view" if self.request.method == "GET" else "cbt.exams.assign"
        return [IsAuthenticated(), HasSchoolPermission(), HasActiveServiceEntitlement()]

    def get(self, request, examination_id, **kwargs):
        exam = Examination.objects.filter(pk=examination_id, school=self.get_school()).first()
        if not exam:
            raise Http404
        queryset = ExaminationAssignment.objects.filter(examination=exam).select_related("student")
        paginator = CbtPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ExaminationAssignmentSerializer(page, many=True).data)

    def post(self, request, examination_id, **kwargs):
        serializer = AssignmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = assign_examination(
                examination_id,
                self.get_school(),
                request.user,
                student_ids=serializer.validated_data.get("student_ids"),
                all_students=serializer.validated_data["all_students"],
            )
        except (DjangoValidationError, Examination.DoesNotExist) as exc:
            if isinstance(exc, Examination.DoesNotExist):
                raise Http404 from exc
            self.raise_validation(exc)
        return Response(result, status=status.HTTP_201_CREATED if result["assigned"] else status.HTTP_200_OK)


class CbtSetupView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.exams.view"

    def get(self, request, **kwargs):
        school = self.get_school()
        sessions = AcademicSession.objects.filter(school=school).order_by("-start_date")
        classes = ClassLevel.objects.filter(school=school, is_active=True)
        subjects = Subject.objects.filter(school=school, is_active=True)
        terms = Term.objects.filter(school=school).select_related("academic_session")
        eligible_students = []
        class_id = request.query_params.get("class_level")
        session_id = request.query_params.get("academic_session")
        if class_id and session_id:
            try:
                class_id = int(class_id)
                session_id = int(session_id)
            except (TypeError, ValueError) as exc:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("Class and academic session must be valid identifiers.") from exc
            if not ClassLevel.objects.filter(pk=class_id, school=school, is_active=True).exists():
                raise Http404
            if not AcademicSession.objects.filter(pk=session_id, school=school).exists():
                raise Http404
            enrollments = StudentEnrollment.objects.filter(
                school=school,
                class_level_id=class_id,
                academic_session_id=session_id,
                status=StudentEnrollment.Status.ACTIVE,
                student__status=Student.Status.ACTIVE,
            ).select_related("student").order_by("student__last_name", "student__first_name")
            eligible_students = [{
                "id": enrollment.student_id,
                "name": " ".join(p for p in (enrollment.student.first_name, enrollment.student.middle_name, enrollment.student.last_name) if p),
                "admission_number": enrollment.student.admission_number,
            } for enrollment in enrollments]
        return Response({
            "classes": [{"id": item.pk, "name": item.name} for item in classes],
            "subjects": [{"id": item.pk, "name": item.name} for item in subjects],
            "sessions": [{"id": item.pk, "name": item.name, "start_date": item.start_date, "end_date": item.end_date} for item in sessions],
            "terms": [{"id": item.pk, "name": item.name, "academic_session": item.academic_session_id, "start_date": item.start_date, "end_date": item.end_date} for item in terms],
            "eligible_students": eligible_students,
        })


class ExaminationPackageView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.exams.publish"

    def post(self, request, examination_id, **kwargs):
        try:
            package = create_examination_package(examination_id, self.get_school(), request.user)
        except (DjangoValidationError, Examination.DoesNotExist) as exc:
            if isinstance(exc, Examination.DoesNotExist):
                raise Http404 from exc
            self.raise_validation(exc)
        return Response({
            "package_id": str(package.package_id),
            "examination_id": str(package.examination_id),
            "version": package.version,
            "payload_hash": package.payload_hash,
            "signed_payload": package.signed_payload,
            "created_at": package.created_at,
        }, status=status.HTTP_201_CREATED)

    def get(self, request, examination_id, **kwargs):
        package = CbtExaminationPackage.objects.filter(examination_id=examination_id, school=self.get_school()).first()
        if not package:
            raise Http404
        return Response({
            "package_id": str(package.package_id), "examination_id": str(package.examination_id),
            "version": package.version, "payload_hash": package.payload_hash,
            "signed_payload": package.signed_payload, "created_at": package.created_at,
        })


class LocalServerCredentialView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "services.manage"

    def post(self, request, **kwargs):
        name = str(request.data.get("name", "")).strip()
        if not name or len(name) > 100:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"name": "Provide a server name up to 100 characters."})
        credential, token = issue_local_server_credential(self.get_school(), name)
        return Response({"id": credential.pk, "name": credential.name, "token": token, "created_at": credential.created_at}, status=status.HTTP_201_CREATED)


class LocalServerListView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "services.view"

    def get(self, request, **kwargs):
        rows = LocalCbtServerCredential.objects.filter(school=self.get_school()).order_by("name")
        return Response([{
            "id": row.pk, "name": row.name, "is_active": row.is_active,
            "last_seen_at": row.last_seen_at, "created_at": row.created_at,
        } for row in rows])


class LocalServerRevokeView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "services.manage"

    def post(self, request, server_id, **kwargs):
        server = LocalCbtServerCredential.objects.filter(pk=server_id, school=self.get_school()).first()
        if not server:
            raise Http404
        server.is_active = False
        server.save(update_fields=("is_active",))
        return Response({"id": server.pk, "is_active": False})


class CbtSyncIngestView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "cbt_sync"

    def post(self, request, **kwargs):
        if not isinstance(request.data, dict):
            return Response({"detail": "A JSON synchronization envelope is required."}, status=status.HTTP_400_BAD_REQUEST)
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return Response({"detail": "Local server credential required."}, status=status.HTTP_401_UNAUTHORIZED)
        bearer_token = authorization[7:].strip()
        credential = LocalCbtServerCredential.authenticate_token(bearer_token)
        if not credential:
            return Response({"detail": "Local server credential is invalid or revoked."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            event, created, conflict = ingest_local_submission(credential, request.data, bearer_token)
        except DjangoValidationError as exc:
            details = getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])
            return Response({"detail": details}, status=status.HTTP_409_CONFLICT if "event_id" in getattr(exc, "message_dict", {}) or "local_session_id" in getattr(exc, "message_dict", {}) else status.HTTP_400_BAD_REQUEST)
        if conflict:
            return Response({"event_id": str(event.event_id), "status": event.status, "accepted": False, "detail": event.resolution_note}, status=status.HTTP_409_CONFLICT)
        return Response({"event_id": str(event.event_id), "status": event.status, "accepted": True, "duplicate": not created})


class CbtSyncDashboardView(CbtSchoolViewMixin, APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission, HasActiveServiceEntitlement)
    required_school_permission = "cbt.exams.view"

    def get(self, request, **kwargs):
        school = self.get_school()
        events = LocalCbtSyncEvent.objects.filter(school=school).select_related("examination", "assignment__student")
        return Response({
            "local_servers": list(LocalCbtServerCredential.objects.filter(school=school).values("id", "name", "is_active", "last_seen_at")),
            "accepted": events.filter(status=LocalCbtSyncEvent.Status.ACCEPTED).count(),
            "conflicts": events.filter(status=LocalCbtSyncEvent.Status.CONFLICT).count(),
            "submissions": CbtSyncedSubmission.objects.filter(school=school).count(),
            "recent_events": [{
                "event_id": str(item.event_id), "examination": item.examination.title,
                "student": item.assignment.student.admission_number, "status": item.status,
                "received_at": item.received_at, "local_session_id": str(item.local_session_id),
            } for item in events[:100]],
        })
