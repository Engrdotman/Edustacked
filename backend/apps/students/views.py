from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from apps.schools.tenancy import SchoolScopedQuerySetMixin
from .models import Guardian, Student, StudentEnrollment, StudentGuardian
from .permissions import HasStudentPermission
from .serializers import (
    EnrollmentCreateSerializer, EnrollmentReadSerializer, EnrollmentTransferSerializer,
    EnrollmentTransitionSerializer, GuardianSerializer, StudentAdmissionSerializer,
    StudentContactSerializer, StudentCreateSerializer, StudentGuardianCreateSerializer,
    StudentGuardianReadSerializer, StudentGuardianUpdateSerializer, StudentManageSerializer,
    StudentPhotoSerializer, StudentRosterSerializer,
)


class StudentPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def teacher_assignment_contexts(user, school):
    from apps.staff.models import TeacherAssignment
    return list(TeacherAssignment.objects.filter(
        school=school, teacher__staff__user=user, status=TeacherAssignment.Status.ACTIVE,
    ).values_list("academic_session_id", "class_level_id", "class_arm_id"))


def scope_students_to_teacher(queryset, user, school):
    allowed = Q(pk__in=[])
    for session_id, class_id, arm_id in teacher_assignment_contexts(user, school):
        allowed |= Q(enrollments__school=school, enrollments__status=StudentEnrollment.Status.ACTIVE,
                     enrollments__academic_session_id=session_id, enrollments__class_level_id=class_id,
                     enrollments__class_arm_id=arm_id)
    return queryset.filter(allowed).distinct()


def scope_enrollments_to_teacher(queryset, user, school):
    allowed = Q(pk__in=[])
    for session_id, class_id, arm_id in teacher_assignment_contexts(user, school):
        allowed |= Q(academic_session_id=session_id, class_level_id=class_id, class_arm_id=arm_id,
                     status=StudentEnrollment.Status.ACTIVE)
    return queryset.filter(allowed)


class StudentViewMixin(SchoolScopedQuerySetMixin):
    permission_classes = (IsAuthenticated, HasStudentPermission)
    pagination_class = StudentPagination

    def get_serializer_context(self):
        context = {"request": self.request, "format": self.format_kwarg, "view": self}
        context["school"] = self.get_authorized_school()
        return context

    def role(self):
        if self.request.user.is_superuser:
            return "school_admin"
        from apps.schools.permissions import authorized_membership
        return authorized_membership(self.request.user, self.request, self).role


class AdmissionCreateView(StudentViewMixin, APIView):
    student_permissions = {"POST": "students.enroll"}

    def post(self, request, **kwargs):
        serializer = StudentAdmissionSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StudentListCreateView(StudentViewMixin, ListCreateAPIView):
    queryset = Student.objects.all()
    student_permissions = {"GET": "students.view", "POST": "students.enroll"}

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("enrollments__class_level", "enrollments__class_arm")
        if self.role() == "teacher":
            queryset = scope_students_to_teacher(queryset, self.request.user, self.get_authorized_school())
        params = self.request.query_params
        search = params.get("search", "").strip()
        if len(search) > 100:
            raise serializers.ValidationError({"search": "Search must be 100 characters or fewer."})
        if search:
            from django.db.models import Q
            queryset = queryset.filter(Q(admission_number__icontains=search) | Q(first_name__icontains=search) | Q(middle_name__icontains=search) | Q(last_name__icontains=search))
        if params.get("status"):
            valid_statuses = [value for value, label in Student.Status.choices]
            if params["status"] not in valid_statuses:
                raise serializers.ValidationError({"status": f"Status must be one of: {', '.join(valid_statuses)}."})
            queryset = queryset.filter(status=params["status"])
        for key, field in (("academic_session", "enrollments__academic_session_id"), ("class_level", "enrollments__class_level_id"), ("class_arm", "enrollments__class_arm_id")):
            value = params.get(key)
            if value:
                if not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                queryset = queryset.filter(**{field: int(value), "enrollments__status": StudentEnrollment.Status.ACTIVE})
        return queryset.distinct()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StudentCreateSerializer
        role = self.role()
        return StudentRosterSerializer if role == "teacher" else StudentContactSerializer if role == "receptionist" else StudentManageSerializer

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school())


class StudentDetailView(StudentViewMixin, RetrieveUpdateAPIView):
    queryset = Student.objects.all()
    student_permissions = {"GET": "students.view", "PATCH": "students.manage", "PUT": "students.manage"}
    http_method_names = ("get", "patch", "head", "options")

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.role() == "teacher":
            queryset = scope_students_to_teacher(queryset, self.request.user, self.get_authorized_school())
        return queryset

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return StudentManageSerializer
        role = self.role()
        return StudentRosterSerializer if role == "teacher" else StudentContactSerializer if role == "receptionist" else StudentManageSerializer


class GuardianListCreateView(StudentViewMixin, ListCreateAPIView):
    queryset = Guardian.objects.all()
    student_permissions = {"GET": "students.guardians.view", "POST": "students.guardians.manage"}
    serializer_class = GuardianSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            if len(search) > 100:
                raise serializers.ValidationError({"search": "Search must be 100 characters or fewer."})
            from django.db.models import Q
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))
        return qs

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school())


class GuardianDetailView(StudentViewMixin, RetrieveUpdateAPIView):
    queryset = Guardian.objects.all()
    serializer_class = GuardianSerializer
    student_permissions = {"GET": "students.guardians.view", "PATCH": "students.guardians.manage"}
    http_method_names = ("get", "patch", "head", "options")

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        guardian = serializer.save()
        if was_active and not guardian.is_active:
            from apps.parent_portal.models import PortalAuditEvent
            PortalAuditEvent.objects.create(actor=self.request.user, guardian=guardian, action="guardian_portal_access_revoked")


class StudentGuardianListCreateView(StudentViewMixin, ListCreateAPIView):
    queryset = StudentGuardian.objects.select_related("guardian")
    student_permissions = {"GET": "students.guardians.view", "POST": "students.guardians.manage"}

    def get_student(self):
        queryset = Student.objects.filter(school=self.get_authorized_school())
        if self.role() == "teacher":
            queryset = scope_students_to_teacher(queryset, self.request.user, self.get_authorized_school())
        return get_object_or_404(queryset, pk=self.kwargs["student_id"])

    def get_queryset(self):
        return super().get_queryset().filter(student=self.get_student(), is_active=True)

    def get_serializer_class(self):
        return StudentGuardianReadSerializer if self.request.method == "GET" else StudentGuardianCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(school=self.get_authorized_school(), student=self.get_student())
        return context

    def perform_create(self, serializer):
        serializer.save()


class StudentGuardianDetailView(StudentViewMixin, RetrieveUpdateAPIView):
    queryset = StudentGuardian.objects.select_related("guardian", "student")
    student_permissions = {"GET": "students.guardians.view", "PATCH": "students.guardians.manage", "DELETE": "students.guardians.manage"}
    http_method_names = ("get", "patch", "delete", "head", "options")

    def get_queryset(self):
        return super().get_queryset().filter(student_id=self.kwargs["student_id"], is_active=True)

    def get_serializer_class(self):
        return StudentGuardianReadSerializer if self.request.method == "GET" else StudentGuardianUpdateSerializer

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        link = serializer.save()
        if was_active and not link.is_active:
            from apps.parent_portal.models import PortalAuditEvent
            PortalAuditEvent.objects.create(actor=self.request.user, guardian=link.guardian, student_link=link, action="guardian_student_link_revoked")

    def delete(self, request, *args, **kwargs):
        link = self.get_object()
        link.is_active = False
        link.is_primary_contact = False
        link.save()
        from apps.parent_portal.models import PortalAuditEvent
        PortalAuditEvent.objects.create(actor=request.user, guardian=link.guardian, student_link=link, action="guardian_student_link_revoked")
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentEnrollmentListCreateView(StudentViewMixin, ListCreateAPIView):
    queryset = StudentEnrollment.objects.select_related("academic_session", "class_level", "class_arm")
    student_permissions = {"GET": "students.view", "POST": "students.enroll"}

    def get_student(self):
        queryset = Student.objects.filter(school=self.get_authorized_school())
        if self.role() == "teacher":
            queryset = scope_students_to_teacher(queryset, self.request.user, self.get_authorized_school())
        return get_object_or_404(queryset, pk=self.kwargs["student_id"])

    def get_queryset(self):
        queryset = super().get_queryset().filter(student=self.get_student())
        if self.role() == "teacher":
            queryset = scope_enrollments_to_teacher(queryset, self.request.user, self.get_authorized_school())
        return queryset

    def get_serializer_class(self):
        return EnrollmentReadSerializer if self.request.method == "GET" else EnrollmentCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(school=self.get_authorized_school(), student=self.get_student())
        return context

    def perform_create(self, serializer):
        serializer.save()


class EnrollmentDetailView(StudentViewMixin, RetrieveAPIView):
    queryset = StudentEnrollment.objects.select_related("academic_session", "class_level", "class_arm")
    serializer_class = EnrollmentReadSerializer
    student_permissions = {"GET": "students.view"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.role() == "teacher":
            queryset = scope_enrollments_to_teacher(queryset, self.request.user, self.get_authorized_school())
        return queryset


class EnrollmentTransitionView(StudentViewMixin, APIView):
    student_permissions = {"POST": "students.enroll"}

    def post(self, request, pk, **kwargs):
        enrollment = get_object_or_404(StudentEnrollment.objects.select_related("student"), school=self.get_authorized_school(), pk=pk)
        serializer = EnrollmentTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["status"] == StudentEnrollment.Status.WITHDRAWN:
            enrollment.withdrawal_date = data.get("withdrawal_date")
            enrollment.withdrawal_reason = data.get("withdrawal_reason", "")
        try:
            with transaction.atomic():
                enrollment.status = data["status"]
                enrollment.save()
        except (DjangoValidationError, IntegrityError) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Invalid enrollment transition."
            raise serializers.ValidationError(detail) from exc
        return Response(EnrollmentReadSerializer(enrollment).data)


class EnrollmentTransferView(StudentViewMixin, APIView):
    student_permissions = {"POST": "students.enroll"}

    def post(self, request, pk, **kwargs):
        school = self.get_authorized_school()
        current = get_object_or_404(StudentEnrollment.objects.select_related("student", "academic_session"), school=school, pk=pk)
        serializer = EnrollmentTransferSerializer(data=request.data, context={"request": request, "school": school})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                current = StudentEnrollment.objects.select_for_update().get(pk=current.pk)
                if current.status != StudentEnrollment.Status.ACTIVE:
                    raise serializers.ValidationError({"status": "Only an active enrollment can be transferred."})
                current.status = StudentEnrollment.Status.TRANSFERRED
                current.transfer_date = data["transfer_date"]
                current.transfer_reason = data["reason"]
                current.save()
                new = StudentEnrollment.objects.create(
                    school=school, student=current.student, academic_session=current.academic_session,
                    class_level=data["class_level"], class_arm=data["class_arm"],
                    enrollment_date=data["transfer_date"], status=StudentEnrollment.Status.ACTIVE,
                    previous_enrollment=current,
                )
        except (DjangoValidationError, IntegrityError) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Transfer could not be completed."
            raise serializers.ValidationError(detail) from exc
        return Response(EnrollmentReadSerializer(new).data, status=status.HTTP_201_CREATED)


class StudentPhotoView(StudentViewMixin, APIView):
    student_permissions = {"GET": "students.manage", "POST": "students.manage"}
    parser_classes = (MultiPartParser, FormParser)

    def get_student(self):
        return get_object_or_404(Student.objects.filter(school=self.get_authorized_school()), pk=self.kwargs["pk"])

    def get(self, request, pk, **kwargs):
        student = self.get_student()
        if not student.photo:
            raise Http404
        try:
            student.photo.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404 from None
        return FileResponse(student.photo, content_type="application/octet-stream", filename=f"student-{student.pk}-photo")

    def post(self, request, pk, **kwargs):
        student = self.get_student()
        serializer = StudentPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student.photo = serializer.validated_data["photo"]
        student.save(update_fields=("photo", "updated_at"))
        return Response({"photo_present": True}, status=status.HTTP_200_OK)
