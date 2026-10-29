from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.schools.permissions import HasSchoolPermission
from apps.schools.tenancy import SchoolScopedQuerySetMixin

from .models import AcademicSession, ClassArm, ClassLevel, ClassSubject, GradeBand, GradingScale, Subject, Term
from .serializers import (
    AcademicSessionSerializer, ClassArmSerializer, ClassLevelSerializer,
    ClassSubjectSerializer, GradeBandSerializer, GradingScaleSerializer,
    SubjectSerializer, TermSerializer,
)


class AcademicPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AcademicConfigMixin(SchoolScopedQuerySetMixin):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "academics.manage"
    pagination_class = AcademicPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["school"] = self.get_authorized_school()
        return context


class SafeDeactivateMixin:
    """Use deactivation for reusable configuration instead of deleting it."""

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not getattr(instance, "is_active", False):
            return Response(status=status.HTTP_204_NO_CONTENT)
        instance.is_active = False
        try:
            instance.save()
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", None) or exc.messages
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcademicSessionListCreateView(AcademicConfigMixin, ListCreateAPIView):
    queryset = AcademicSession.objects.select_related("school")
    serializer_class = AcademicSessionSerializer


class AcademicSessionDetailView(AcademicConfigMixin, RetrieveUpdateDestroyAPIView):
    queryset = AcademicSession.objects.select_related("school")
    serializer_class = AcademicSessionSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != AcademicSession.Status.DRAFT or instance.terms.exists():
            return Response(
                {"detail": "Only a draft session with no terms can be deleted."},
                status=status.HTTP_409_CONFLICT,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TermListCreateView(AcademicConfigMixin, ListCreateAPIView):
    queryset = Term.objects.select_related("school", "academic_session")
    serializer_class = TermSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        session_id = self.request.query_params.get("academic_session")
        if not session_id:
            return queryset
        if not session_id.isdecimal():
            raise serializers.ValidationError({"academic_session": "Use a valid session ID."})
        return queryset.filter(academic_session_id=int(session_id))

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school())


class TermDetailView(AcademicConfigMixin, RetrieveUpdateDestroyAPIView):
    queryset = Term.objects.select_related("school", "academic_session")
    serializer_class = TermSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != Term.Status.DRAFT:
            return Response(
                {"detail": "Only a draft term can be deleted; complete terms to preserve their history."},
                status=status.HTTP_409_CONFLICT,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClassLevelListCreateView(AcademicConfigMixin, ListCreateAPIView):
    queryset = ClassLevel.objects.select_related("school")
    serializer_class = ClassLevelSerializer


class ClassLevelDetailView(AcademicConfigMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    queryset = ClassLevel.objects.select_related("school")
    serializer_class = ClassLevelSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")


class SubjectListCreateView(AcademicConfigMixin, ListCreateAPIView):
    queryset = Subject.objects.select_related("school")
    serializer_class = SubjectSerializer


class SubjectDetailView(AcademicConfigMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    queryset = Subject.objects.select_related("school")
    serializer_class = SubjectSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")


class ClassArmNestedMixin(AcademicConfigMixin):
    queryset = ClassArm.objects.select_related("school", "class_level")
    serializer_class = ClassArmSerializer
    def get_class_level(self):
        school = self.get_authorized_school()
        return get_object_or_404(
            ClassLevel.objects.filter(school=school), pk=self.kwargs.get("class_id")
        )

    def get_queryset(self):
        return super().get_queryset().filter(class_level=self.get_class_level())

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school(), class_level=self.get_class_level())


class ClassArmListCreateView(ClassArmNestedMixin, ListCreateAPIView):
    pass


class ClassArmDetailView(ClassArmNestedMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    http_method_names = ("get", "patch", "delete", "head", "options")


class ClassSubjectNestedMixin(AcademicConfigMixin):
    queryset = ClassSubject.objects.select_related("school", "class_level", "subject")
    serializer_class = ClassSubjectSerializer

    def get_class_level(self):
        school = self.get_authorized_school()
        return get_object_or_404(
            ClassLevel.objects.filter(school=school), pk=self.kwargs.get("class_id")
        )

    def get_queryset(self):
        return super().get_queryset().filter(class_level=self.get_class_level())

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school(), class_level=self.get_class_level())


class ClassSubjectListCreateView(ClassSubjectNestedMixin, ListCreateAPIView):
    pass


class ClassSubjectDetailView(ClassSubjectNestedMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    http_method_names = ("get", "patch", "delete", "head", "options")


class GradingScaleListCreateView(AcademicConfigMixin, ListCreateAPIView):
    queryset = GradingScale.objects.select_related("school")
    serializer_class = GradingScaleSerializer


class GradingScaleDetailView(AcademicConfigMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    queryset = GradingScale.objects.select_related("school")
    serializer_class = GradingScaleSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")


class GradeBandNestedMixin(AcademicConfigMixin):
    queryset = GradeBand.objects.select_related("school", "grading_scale")
    serializer_class = GradeBandSerializer

    def get_grading_scale(self):
        school = self.get_authorized_school()
        return get_object_or_404(GradingScale.objects.filter(school=school), pk=self.kwargs.get("scale_id"))

    def get_queryset(self):
        return super().get_queryset().filter(grading_scale=self.get_grading_scale())

    def perform_create(self, serializer):
        serializer.save(school=self.get_authorized_school(), grading_scale=self.get_grading_scale())


class GradeBandListCreateView(GradeBandNestedMixin, ListCreateAPIView):
    pass


class GradeBandDetailView(GradeBandNestedMixin, SafeDeactivateMixin, RetrieveUpdateDestroyAPIView):
    http_method_names = ("get", "patch", "delete", "head", "options")
