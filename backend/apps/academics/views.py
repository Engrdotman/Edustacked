from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.permissions import HasSchoolPermission
from apps.schools.tenancy import SchoolScopedQuerySetMixin

from .models import AcademicSession, ClassArm, ClassLevel, ClassSubject, GradeBand, GradingScale, PromotionCriteria, Subject, Term
from .serializers import (
    AcademicSessionSerializer, ClassArmSerializer, ClassLevelSerializer,
    ClassSubjectSerializer, GradeBandSerializer, GradingScaleSerializer, PromotionCriteriaSerializer,
    SubjectSerializer, TermSerializer,
)


class CopyAcademicSetupSerializer(serializers.Serializer):
    source_session = serializers.IntegerField(min_value=1)
    copy_assessment_plans = serializers.BooleanField(default=True)
    copy_teaching_assignments = serializers.BooleanField(default=True)


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


class AcademicSessionCopySetupView(AcademicConfigMixin, APIView):
    """Carry a prior session's working configuration into a new draft session."""

    def post(self, request, pk, **kwargs):
        school = self.get_authorized_school()
        target = get_object_or_404(AcademicSession, school=school, pk=pk)
        serializer = CopyAcademicSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = get_object_or_404(
            AcademicSession.objects.filter(school=school),
            pk=serializer.validated_data["source_session"],
        )
        if target.pk == source.pk:
            raise serializers.ValidationError({"source_session": "Choose a different session to copy from."})
        if target.status != AcademicSession.Status.DRAFT:
            return Response(
                {"detail": "Select a new draft session as the destination before copying setup."},
                status=status.HTTP_409_CONFLICT,
            )
        if target.terms.exists() or target.assessment_plans.exists() or target.teacher_assignments.exists():
            return Response(
                {"detail": "This session already has terms, assessment plans, or teaching assignments. Copying is only available to a new empty session."},
                status=status.HTTP_409_CONFLICT,
            )

        source_terms = list(source.terms.order_by("sequence", "pk"))
        if not source_terms:
            raise serializers.ValidationError({"source_session": "The selected session has no terms to copy."})
        date_shift = target.start_date - source.start_date
        shifted_terms = [
            (term, term.start_date + date_shift, term.end_date + date_shift)
            for term in source_terms
        ]
        if any(start < target.start_date or end > target.end_date for _, start, end in shifted_terms):
            raise serializers.ValidationError({
                "detail": "The shifted term dates do not fit inside the new session dates. Adjust the new session dates or configure its terms manually."
            })

        from apps.results.models import AssessmentPlan, PlanComponent
        from apps.staff.models import TeacherAssignment

        term_map = {}
        assessment_plans_created = 0
        assessment_plans_skipped = 0
        teaching_assignments_created = 0
        teaching_assignments_skipped = 0
        values = serializer.validated_data

        with transaction.atomic():
            for source_term, start_date, end_date in shifted_terms:
                copied_term = Term.objects.create(
                    school=school,
                    academic_session=target,
                    name=source_term.name,
                    sequence=source_term.sequence,
                    start_date=start_date,
                    end_date=end_date,
                    status=Term.Status.DRAFT,
                )
                term_map[source_term.pk] = copied_term

            if values["copy_assessment_plans"]:
                plans = AssessmentPlan.objects.filter(
                    school=school, academic_session=source,
                ).select_related("term").prefetch_related("components").order_by("pk")
                for source_plan in plans:
                    try:
                        with transaction.atomic():
                            copied_plan = AssessmentPlan(
                                school=school,
                                academic_session=target,
                                term=term_map[source_plan.term_id],
                                class_level=source_plan.class_level,
                                class_arm=source_plan.class_arm,
                                subject=source_plan.subject,
                                grading_scale=source_plan.grading_scale,
                                name=source_plan.name,
                                calculation_method=source_plan.calculation_method,
                                grading_scale_snapshot=source_plan.grading_scale_snapshot,
                                status=AssessmentPlan.Status.DRAFT,
                                created_by=request.user,
                            )
                            copied_plan.save()
                            for component in source_plan.components.all():
                                PlanComponent.objects.create(
                                    plan=copied_plan,
                                    component=component.component,
                                    max_score=component.max_score,
                                    weight=component.weight,
                                    position=component.position,
                                )
                        assessment_plans_created += 1
                    except (DjangoValidationError, IntegrityError):
                        assessment_plans_skipped += 1

            if values["copy_teaching_assignments"]:
                assignments = TeacherAssignment.objects.filter(
                    school=school,
                    academic_session=source,
                    status=TeacherAssignment.Status.ACTIVE,
                ).select_related("teacher", "class_level", "class_arm", "subject")
                for source_assignment in assignments:
                    start_date = source_assignment.start_date + date_shift
                    end_date = source_assignment.end_date + date_shift if source_assignment.end_date else None
                    if (
                        start_date < target.start_date
                        or start_date > target.end_date
                        or (end_date and end_date > target.end_date)
                    ):
                        teaching_assignments_skipped += 1
                        continue
                    try:
                        with transaction.atomic():
                            TeacherAssignment.objects.create(
                                school=school,
                                teacher=source_assignment.teacher,
                                academic_session=target,
                                class_level=source_assignment.class_level,
                                class_arm=source_assignment.class_arm,
                                subject=source_assignment.subject,
                                start_date=start_date,
                                end_date=end_date,
                                status=TeacherAssignment.Status.ACTIVE,
                            )
                        teaching_assignments_created += 1
                    except (DjangoValidationError, IntegrityError):
                        teaching_assignments_skipped += 1

        return Response({
            "detail": "The previous session's setup was copied. Review the new term dates, teaching assignments, and draft assessment plans before activating them.",
            "source_session": source.name,
            "target_session": target.name,
            "terms_created": len(term_map),
            "assessment_plans_created": assessment_plans_created,
            "assessment_plans_skipped": assessment_plans_skipped,
            "teaching_assignments_created": teaching_assignments_created,
            "teaching_assignments_skipped": teaching_assignments_skipped,
            "student_records_copied": 0,
            "results_copied": 0,
            "attendance_copied": 0,
        }, status=status.HTTP_201_CREATED)


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


class ClassPromotionCriteriaView(AcademicConfigMixin, APIView):
    """Read or update the pass threshold used for promotion recommendations."""

    def get_class_level(self):
        return get_object_or_404(
            ClassLevel.objects.filter(school=self.get_authorized_school()),
            pk=self.kwargs["class_id"],
        )

    def get(self, request, *args, **kwargs):
        class_level = self.get_class_level()
        criteria = PromotionCriteria.objects.filter(class_level=class_level).first()
        if not criteria:
            return Response({
                "configured": False,
                "class_level": class_level.pk,
                "class_name": class_level.name,
                "minimum_subjects_passed": 1,
                "pass_mark": "40.00",
            })
        data = PromotionCriteriaSerializer(criteria).data
        data["configured"] = True
        return Response(data)

    def post(self, request, *args, **kwargs):
        class_level = self.get_class_level()
        if PromotionCriteria.objects.filter(class_level=class_level).exists():
            return Response({"detail": "Promotion criteria already exist for this class. Edit the existing criteria instead."}, status=status.HTTP_409_CONFLICT)
        return self.save_criteria(request, class_level)

    def put(self, request, *args, **kwargs):
        return self.patch(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        class_level = self.get_class_level()
        criteria = PromotionCriteria.objects.filter(class_level=class_level).first()
        if not criteria:
            return Response({"detail": "Save promotion criteria for this class before editing them."}, status=status.HTTP_404_NOT_FOUND)
        return self.save_criteria(request, class_level, criteria=criteria, partial=True)

    def delete(self, request, *args, **kwargs):
        class_level = self.get_class_level()
        deleted, _ = PromotionCriteria.objects.filter(class_level=class_level).delete()
        if not deleted:
            return Response({"detail": "No promotion criteria are configured for this class."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def save_criteria(self, request, class_level, criteria=None, partial=False):
        serializer = PromotionCriteriaSerializer(
            criteria,
            data=request.data,
            partial=partial,
            context={"request": request, "school": self.get_authorized_school()},
        )
        serializer.is_valid(raise_exception=True)
        saved = serializer.save(school=self.get_authorized_school(), class_level=class_level)
        data = PromotionCriteriaSerializer(saved).data
        data["configured"] = True
        return Response(data, status=status.HTTP_200_OK if criteria else status.HTTP_201_CREATED)


class PromotionReviewView(AcademicConfigMixin, APIView):
    """Report year-end promote/repeat recommendations without moving enrollments."""

    def get(self, request, *args, **kwargs):
        from apps.results.models import AssessmentPlan, AssessmentResult
        from apps.students.models import StudentEnrollment

        school = self.get_authorized_school()
        class_level = get_object_or_404(ClassLevel.objects.filter(school=school), pk=kwargs["class_id"])
        criteria = PromotionCriteria.objects.filter(class_level=class_level).first()
        if not criteria:
            raise serializers.ValidationError({"criteria": "Set promotion criteria for this class before reviewing students."})

        def query_id(name):
            value = request.query_params.get(name, "")
            if not value.isdecimal():
                raise serializers.ValidationError({name: "Choose a valid option."})
            return int(value)

        session = get_object_or_404(AcademicSession.objects.filter(school=school), pk=query_id("academic_session"))
        term = get_object_or_404(Term.objects.filter(school=school, academic_session=session), pk=query_id("term"))
        arm = get_object_or_404(ClassArm.objects.filter(school=school, class_level=class_level), pk=query_id("class_arm"))
        final_term_sequence = Term.objects.filter(academic_session=session).order_by("-sequence").values_list("sequence", flat=True).first()
        if term.sequence != final_term_sequence:
            raise serializers.ValidationError({"term": "Promotion is reviewed from the final term of the academic session."})
        if term.status != Term.Status.COMPLETED:
            raise serializers.ValidationError({"term": "Complete the final term and approve its results before reviewing promotion."})

        class_subjects = list(ClassSubject.objects.filter(
            school=school, class_level=class_level, is_active=True, subject__is_active=True,
        ).select_related("subject").order_by("subject__name"))
        subject_ids = [row.subject_id for row in class_subjects]
        if not subject_ids:
            raise serializers.ValidationError({"class": "Assign active subjects to this class before reviewing promotion."})
        if criteria.minimum_subjects_passed > len(subject_ids):
            raise serializers.ValidationError({
                "criteria": f"The pass requirement is {criteria.minimum_subjects_passed}, but this class currently has only {len(subject_ids)} active subjects. Update the class criteria first."
            })

        enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_session=session,
            class_level=class_level,
            class_arm=arm,
            status__in=(StudentEnrollment.Status.ACTIVE, StudentEnrollment.Status.COMPLETED),
            enrollment_date__lte=term.end_date,
            student__status="active",
        ).select_related("student", "class_level", "class_arm").order_by(
            "student__last_name", "student__first_name", "student__id",
        )
        all_enrollments = list(enrollments)
        paginator = AcademicPagination()
        page = paginator.paginate_queryset(all_enrollments, request, view=self)
        page_ids = {row.pk for row in page}
        enrollment_ids = [row.pk for row in all_enrollments]
        subject_names = {row.subject_id: row.subject.name for row in class_subjects}
        plans = AssessmentPlan.objects.filter(
            school=school,
            academic_session=session,
            term=term,
            class_level=class_level,
            class_arm=arm,
            subject_id__in=subject_ids,
            status__in=(AssessmentPlan.Status.PUBLISHED, AssessmentPlan.Status.CLOSED),
        )
        results = AssessmentResult.objects.filter(
            school=school,
            enrollment_id__in=enrollment_ids,
            plan__in=plans,
            status=AssessmentResult.Status.APPROVED,
        ).values_list("enrollment_id", "plan__subject_id", "approved_percentage", "approved_grade")
        by_enrollment = {}
        for enrollment_id, subject_id, percentage, grade in results:
            by_enrollment.setdefault(enrollment_id, {}).setdefault(subject_id, []).append((percentage, grade))

        recommendations = []
        pass_mark = Decimal(criteria.pass_mark)
        for enrollment in all_enrollments:
            subject_results = by_enrollment.get(enrollment.pk, {})
            missing = []
            duplicate = []
            scored = []
            passed = 0
            for subject_id in subject_ids:
                entries = subject_results.get(subject_id, [])
                if not entries:
                    missing.append(subject_names[subject_id])
                elif len(entries) > 1:
                    duplicate.append(subject_names[subject_id])
                else:
                    percentage, grade = entries[0]
                    if percentage is None:
                        missing.append(subject_names[subject_id])
                    else:
                        passed_subject = Decimal(percentage) >= pass_mark
                        passed += int(passed_subject)
                        scored.append({
                            "subject": subject_names[subject_id],
                            "percentage": str(percentage),
                            "grade": grade,
                            "passed": passed_subject,
                        })
            if missing or duplicate:
                decision = "manual_review"
            elif passed >= criteria.minimum_subjects_passed:
                decision = "promote"
            else:
                decision = "repeat"
            recommendations.append({
                "enrollment_id": enrollment.pk,
                "student_id": enrollment.student_id,
                "student_name": " ".join(part for part in (enrollment.student.first_name, enrollment.student.middle_name, enrollment.student.last_name) if part),
                "admission_number": enrollment.student.admission_number,
                "class_name": enrollment.class_level.name,
                "arm_name": enrollment.class_arm.name,
                "subjects_passed": passed,
                "subjects_required": criteria.minimum_subjects_passed,
                "subjects_total": len(subject_ids),
                "decision": decision,
                "missing_subjects": missing,
                "multiple_approved_results": duplicate,
                "subject_results": scored,
            })
        decision_counts = {
            key: sum(row["decision"] == key for row in recommendations)
            for key in ("promote", "repeat", "manual_review")
        }
        response = paginator.get_paginated_response([
            row for row in recommendations if row["enrollment_id"] in page_ids
        ])
        response.data["review"] = {
            "academic_session": session.name,
            "term": term.name,
            "class_name": class_level.name,
            "arm_name": arm.name,
            "minimum_subjects_passed": criteria.minimum_subjects_passed,
            "pass_mark": str(criteria.pass_mark),
            "active_subjects": len(subject_ids),
            "decision_counts": decision_counts,
            "final_term_required": True,
            "placement_is_automatic": False,
        }
        return response


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
