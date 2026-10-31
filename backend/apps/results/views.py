from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicSession
from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership
from apps.schools.tenancy import SchoolScopedQuerySetMixin
from apps.staff.models import TeacherAssignment, TeacherProfile

from .models import AssessmentComponent, AssessmentPlan, AssessmentResult, ComponentScore, PlanComponent, ResultAuditEvent
from .permissions import HasResultsPermission
from .serializers import (
    AssessmentComponentSerializer, AssessmentPlanSerializer, AssessmentResultSerializer,
    BulkScoreSerializer, PlanComponentSerializer, ResultBatchActionSerializer,
)
from .services import calculate_result, eligible_enrollments, validate_plan_configuration


class ResultsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ResultsMixin(SchoolScopedQuerySetMixin):
    permission_classes = (HasResultsPermission,)
    pagination_class = ResultsPagination

    def school(self):
        return self.get_authorized_school()

    def context(self):
        return {"request": self.request, "view": self, "school": self.school()}

    def role(self):
        if self.request.user.is_superuser:
            return "school_admin"
        return authorized_membership(self.request.user, self.request, self).role

    def teacher_has_plan_assignment(self, plan):
        if self.role() != "teacher":
            return True
        return TeacherAssignment.objects.filter(
            school=plan.school, teacher__staff__user=self.request.user,
            teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
            teacher__staff__status="active", academic_session=plan.academic_session,
            class_level=plan.class_level, class_arm=plan.class_arm, subject=plan.subject,
            status=TeacherAssignment.Status.ACTIVE, start_date__lte=plan.term.end_date,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=plan.term.start_date)).exists()

    def get_plan(self, pk):
        plan = get_object_or_404(AssessmentPlan.objects.select_related(
            "academic_session", "term", "class_level", "class_arm", "subject", "grading_scale", "created_by",
        ).prefetch_related("components__component"), school=self.school(), pk=pk)
        if not self.teacher_has_plan_assignment(plan):
            raise PermissionDenied("You are not assigned to this subject, class, arm, and session.")
        return plan

    def plan_queryset(self):
        queryset = AssessmentPlan.objects.filter(school=self.school()).select_related(
            "academic_session", "term", "class_level", "class_arm", "subject", "grading_scale", "created_by",
        ).prefetch_related("components__component").annotate(result_count=Count("results"))
        if self.role() == "teacher":
            assignments = TeacherAssignment.objects.filter(
                school=self.school(), teacher__staff__user=self.request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", status=TeacherAssignment.Status.ACTIVE,
            )
            assignment_rows = list(assignments.values_list("academic_session_id", "class_level_id", "class_arm_id", "subject_id", "start_date", "end_date"))
            allowed = Q(pk__in=[])
            for session_id, class_id, arm_id, subject_id, start_date, end_date in assignment_rows:
                overlap = Q(term__end_date__gte=start_date)
                if end_date:
                    overlap &= Q(term__start_date__lte=end_date)
                allowed |= Q(academic_session_id=session_id, class_level_id=class_id, class_arm_id=arm_id, subject_id=subject_id) & overlap
            queryset = queryset.filter(allowed).distinct()
        for key, lookup in (("academic_session", "academic_session_id"), ("term", "term_id"), ("class_level", "class_level_id"), ("class_arm", "class_arm_id"), ("subject", "subject_id"), ("status", "status")):
            value = self.request.query_params.get(key)
            if value:
                if key != "status" and not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                queryset = queryset.filter(**{lookup: value})
        return queryset

    def get_result(self, pk):
        result = get_object_or_404(AssessmentResult.objects.select_related(
            "plan", "plan__term", "plan__academic_session", "plan__class_level", "plan__class_arm", "plan__subject", "student", "enrollment",
        ).prefetch_related("scores__plan_component__component", "audit_events__actor"), school=self.school(), pk=pk)
        if not self.teacher_has_plan_assignment(result.plan):
            raise PermissionDenied("You are not assigned to this result.")
        return result


class AssessmentComponentListCreateView(ResultsMixin, APIView):
    result_permissions = {"GET": "academics.manage", "POST": "academics.manage"}

    def get(self, request, **kwargs):
        queryset = AssessmentComponent.objects.filter(school=self.school()).order_by("name")
        page = self.pagination_class().paginate_queryset(queryset, request, view=self)
        return self.pagination_class().get_paginated_response(AssessmentComponentSerializer(page, many=True).data)

    def post(self, request, **kwargs):
        serializer = AssessmentComponentSerializer(data=request.data, context=self.context())
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(AssessmentComponentSerializer(obj).data, status=status.HTTP_201_CREATED)


class AssessmentComponentDetailView(ResultsMixin, APIView):
    result_permissions = {"GET": "academics.manage", "PATCH": "academics.manage"}

    def get_object(self, pk):
        return get_object_or_404(AssessmentComponent, school=self.school(), pk=pk)

    def get(self, request, pk, **kwargs):
        return Response(AssessmentComponentSerializer(self.get_object(pk)).data)

    def patch(self, request, pk, **kwargs):
        obj = self.get_object(pk)
        serializer = AssessmentComponentSerializer(obj, data=request.data, partial=True, context=self.context())
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(AssessmentComponentSerializer(obj).data)


class AssessmentPlanListCreateView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view", "POST": "academics.manage"}

    def get(self, request, **kwargs):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(self.plan_queryset(), request, view=self)
        return paginator.get_paginated_response(AssessmentPlanSerializer(page, many=True, context=self.context()).data)

    def post(self, request, **kwargs):
        serializer = AssessmentPlanSerializer(data=request.data, context=self.context())
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(AssessmentPlanSerializer(plan, context=self.context()).data, status=status.HTTP_201_CREATED)


class AssessmentPlanDetailView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view", "PATCH": "academics.manage"}

    def get(self, request, pk, **kwargs):
        return Response(AssessmentPlanSerializer(self.get_plan(pk), context=self.context()).data)

    def patch(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        serializer = AssessmentPlanSerializer(plan, data=request.data, partial=True, context=self.context())
        serializer.is_valid(raise_exception=True)
        plan = serializer.save(version=plan.version + 1)
        return Response(AssessmentPlanSerializer(plan, context=self.context()).data)


class PlanComponentsView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view", "POST": "academics.manage"}

    def get(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        return Response(PlanComponentSerializer(plan.components.select_related("component").all(), many=True).data)

    def post(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        try:
            with transaction.atomic():
                plan = AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
                serializer = PlanComponentSerializer(data=request.data, context={**self.context(), "plan": plan})
                serializer.is_valid(raise_exception=True)
                component = serializer.save(plan=plan)
                plan.version += 1
                plan.save(update_fields=("version", "updated_at"))
        except (DjangoValidationError, IntegrityError) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "The component configuration conflicts with this plan."
            raise serializers.ValidationError(detail) from exc
        return Response(PlanComponentSerializer(component).data, status=status.HTTP_201_CREATED)


class PlanComponentDetailView(ResultsMixin, APIView):
    result_permissions = {"PATCH": "academics.manage", "DELETE": "academics.manage"}

    def patch(self, request, pk, component_id, **kwargs):
        plan = self.get_plan(pk)
        try:
            with transaction.atomic():
                plan = AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
                component = get_object_or_404(PlanComponent, plan=plan, pk=component_id)
                serializer = PlanComponentSerializer(component, data=request.data, partial=True, context={**self.context(), "plan": plan})
                serializer.is_valid(raise_exception=True)
                component = serializer.save()
                plan.version += 1
                plan.save(update_fields=("version", "updated_at"))
        except (DjangoValidationError, IntegrityError) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "The component configuration conflicts with this plan."
            raise serializers.ValidationError(detail) from exc
        return Response(PlanComponentSerializer(component).data)

    def delete(self, request, pk, component_id, **kwargs):
        plan = self.get_plan(pk)
        try:
            with transaction.atomic():
                plan = AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
                component = get_object_or_404(PlanComponent, plan=plan, pk=component_id)
                component.delete()
                plan.version += 1
                plan.save(update_fields=("version", "updated_at"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class EligiblePlanStudentsView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view"}

    def get(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(eligible_enrollments(plan), request, view=self)
        data = [{"student_id": row.student_id, "student_name": " ".join(x for x in (row.student.first_name, row.student.middle_name, row.student.last_name) if x), "admission_number": row.student.admission_number, "enrollment_id": row.pk} for row in page]
        return paginator.get_paginated_response(data)


class PlanResultsView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view", "PATCH": "results.enter"}

    def get(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        paginator = self.pagination_class()
        enrollments = paginator.paginate_queryset(eligible_enrollments(plan), request, view=self)
        existing = {item.student_id: item for item in AssessmentResult.objects.filter(plan=plan, student_id__in=[row.student_id for row in enrollments]).select_related("student", "enrollment").prefetch_related("scores__plan_component__component", "audit_events__actor")}
        results = []
        for enrollment in enrollments:
            item = existing.get(enrollment.student_id)
            results.append({
                "student_id": enrollment.student_id,
                "student_name": " ".join(x for x in (enrollment.student.first_name, enrollment.student.middle_name, enrollment.student.last_name) if x),
                "admission_number": enrollment.student.admission_number,
                "enrollment_id": enrollment.pk,
                "version": item.version if item else 0,
                "result": AssessmentResultSerializer(item, context=self.context()).data if item else None,
            })
        return paginator.get_paginated_response(results)

    def patch(self, request, pk, **kwargs):
        plan = self.get_plan(pk)
        if plan.status != AssessmentPlan.Status.PUBLISHED:
            raise serializers.ValidationError({"plan": "Scores can only be entered on a published plan."})
        serializer = BulkScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["entries"]
        eligible = {row.student_id: row for row in eligible_enrollments(plan).filter(student_id__in=[x["student_id"] for x in entries])}
        if len(eligible) != len(entries):
            raise serializers.ValidationError({"entries": "One or more students are not eligible for this plan."})
        components = {item.pk: item for item in plan.components.select_related("component")}
        if not components:
            raise serializers.ValidationError({"plan": "Configure components before entering scores."})
        existing = {item.student_id: item for item in AssessmentResult.objects.filter(plan=plan, student_id__in=eligible).prefetch_related("scores")}
        for entry in entries:
            result = existing.get(entry["student_id"])
            expected_version = result.version if result else 0
            if entry["version"] != expected_version:
                return Response({"detail": "This result changed since it was loaded. Reload before saving.", "student_id": entry["student_id"], "current_version": expected_version}, status=status.HTTP_409_CONFLICT)
            if result and result.status != AssessmentResult.Status.DRAFT:
                raise serializers.ValidationError({"entries": f"Result for student {entry['student_id']} is not editable."})
            for score_data in entry["scores"]:
                component = components.get(score_data["plan_component_id"])
                if not component:
                    raise serializers.ValidationError({"entries": "A score references a component outside this plan."})
                if score_data["score"] > component.max_score:
                    raise serializers.ValidationError({"entries": f"Score cannot exceed {component.max_score} for {component.component.name}."})
        try:
            with transaction.atomic():
                locked_plan = AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
                if locked_plan.status != AssessmentPlan.Status.PUBLISHED:
                    raise serializers.ValidationError({"plan": "Scores can only be entered on a published plan."})
                existing = {item.student_id: item for item in AssessmentResult.objects.select_for_update().filter(plan=locked_plan, student_id__in=eligible).prefetch_related("scores")}
                for entry in entries:
                    result = existing.get(entry["student_id"])
                    current_version = result.version if result else 0
                    if entry["version"] != current_version:
                        return Response({"detail": "This result changed since it was loaded. Reload before saving.", "student_id": entry["student_id"], "current_version": current_version}, status=status.HTTP_409_CONFLICT)
                    if result and result.status != AssessmentResult.Status.DRAFT:
                        raise serializers.ValidationError({"entries": f"Result for student {entry['student_id']} is not editable."})
                for entry in entries:
                    enrollment = eligible[entry["student_id"]]
                    result = existing.get(entry["student_id"])
                    if not result:
                        result = AssessmentResult.objects.create(school=plan.school, plan=plan, student=enrollment.student, enrollment=enrollment)
                    previous = {str(score.plan_component_id): str(score.score) for score in result.scores.all()}
                    for item in entry["scores"]:
                        component = components[item["plan_component_id"]]
                        score, created = ComponentScore.objects.get_or_create(
                            result=result, plan_component=component,
                            defaults={"score": item["score"], "recorded_by": request.user, "last_modified_by": request.user},
                        )
                        if not created and score.score != item["score"]:
                            score.score = item["score"]
                            score.last_modified_by = request.user
                            score.save()
                        if created or previous.get(str(component.pk)) != str(item["score"]):
                            ResultAuditEvent.objects.create(
                                school=plan.school, plan=plan, result=result, plan_component=component, actor=request.user,
                                event_type=ResultAuditEvent.EventType.SCORE_RECORDED if created else ResultAuditEvent.EventType.SCORE_CORRECTED,
                                previous_value={"score": previous.get(str(component.pk))}, new_value={"score": str(item["score"])},
                            )
                    result.version += 1
                    result.save(update_fields=("version", "updated_at"))
        except (DjangoValidationError, IntegrityError) as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Unable to save the score batch."
            raise serializers.ValidationError(detail) from exc
        return Response({"detail": "Scores saved.", "results": [{"student_id": item["student_id"], "version": AssessmentResult.objects.get(plan=plan, student_id=item["student_id"]).version} for item in entries]})


class PlanActionView(ResultsMixin, APIView):
    result_action_permissions = {"publish": "academics.manage", "close": "academics.manage", "reopen": "academics.manage"}

    def post(self, request, pk, action, **kwargs):
        plan = self.get_plan(pk)
        reason = str(request.data.get("reason", "")).strip()
        try:
            expected_version = int(request.data.get("version", 0))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"version": "Provide the current plan version."})
        with transaction.atomic():
            plan = AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
            if expected_version != plan.version:
                return Response({"detail": "This plan changed since it was loaded. Reload before continuing.", "current_version": plan.version}, status=status.HTTP_409_CONFLICT)
            if action == "publish":
                if plan.status != AssessmentPlan.Status.DRAFT:
                    raise serializers.ValidationError({"status": "Only a draft plan can be published."})
                try:
                    validate_plan_configuration(plan)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
                plan.status = AssessmentPlan.Status.PUBLISHED
                plan.published_by = request.user
                event = ResultAuditEvent.EventType.PLAN_PUBLISHED
            elif action == "close":
                if plan.status != AssessmentPlan.Status.PUBLISHED:
                    raise serializers.ValidationError({"status": "Only a published plan can be closed."})
                eligible_ids = set(eligible_enrollments(plan).values_list("student_id", flat=True))
                approved_ids = set(plan.results.filter(status=AssessmentResult.Status.APPROVED).values_list("student_id", flat=True))
                if eligible_ids != approved_ids:
                    raise serializers.ValidationError({"results": "Every eligible student must have an approved result before the plan can close."})
                plan.status = AssessmentPlan.Status.CLOSED
                plan.closed_by = request.user
                event = ResultAuditEvent.EventType.PLAN_CLOSED
            elif action == "reopen":
                if plan.status != AssessmentPlan.Status.CLOSED or not reason:
                    raise serializers.ValidationError({"reason": "A closed plan can be reopened only with a reason."})
                plan.status = AssessmentPlan.Status.PUBLISHED
                plan.reopened_by = request.user
                event = ResultAuditEvent.EventType.PLAN_REOPENED
            else:
                return Response({"detail": "Unknown plan action."}, status=status.HTTP_404_NOT_FOUND)
            plan.version += 1
            plan.save()
            ResultAuditEvent.objects.create(school=plan.school, plan=plan, actor=request.user, event_type=event, reason=reason)
        return Response(AssessmentPlanSerializer(plan, context=self.context()).data)


class ResultBatchActionView(ResultsMixin, APIView):
    result_action_permissions = {"submit": "results.enter", "approve": "results.approve", "reopen": "results.approve"}

    def post(self, request, plan_id, action, **kwargs):
        plan = self.get_plan(plan_id)
        serializer = ResultBatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["entries"]
        reason = serializer.validated_data.get("reason", "").strip()
        if action == "reopen" and not reason:
            raise serializers.ValidationError({"reason": "A correction reason is required."})
        result_by_student = {item.student_id: item for item in AssessmentResult.objects.filter(school=plan.school, plan=plan, student_id__in=[x["student_id"] for x in entries]).select_related("student").prefetch_related("scores__plan_component__component")}
        if len(result_by_student) != len(entries):
            raise serializers.ValidationError({"entries": "One or more results do not exist for this plan."})
        for entry in entries:
            result = result_by_student[entry["student_id"]]
            if result.version != entry["version"]:
                return Response({"detail": "A result changed since it was loaded. Reload before continuing.", "student_id": result.student_id, "current_version": result.version}, status=status.HTTP_409_CONFLICT)
            if action == "submit":
                if plan.status != AssessmentPlan.Status.PUBLISHED or result.status != AssessmentResult.Status.DRAFT:
                    raise serializers.ValidationError({"status": "Only draft results on a published plan can be submitted."})
                if not calculate_result(result)["complete"]:
                    raise serializers.ValidationError({"scores": f"Result for {result.student} is missing one or more component scores."})
            elif action == "approve":
                if result.status != AssessmentResult.Status.SUBMITTED:
                    raise serializers.ValidationError({"status": "Only submitted results can be approved."})
                if result.plan.created_by_id == request.user.pk or result.scores.filter(recorded_by=request.user).exists():
                    raise PermissionDenied("You cannot approve results you created or entered.")
            elif action == "reopen":
                if result.status != AssessmentResult.Status.APPROVED:
                    raise serializers.ValidationError({"status": "Only approved results can be reopened."})
            else:
                return Response({"detail": "Unknown result action."}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            AssessmentPlan.objects.select_for_update().get(pk=plan.pk)
            for entry in entries:
                result = AssessmentResult.objects.select_for_update().get(pk=result_by_student[entry["student_id"]].pk)
                if result.version != entry["version"]:
                    return Response({"detail": "A result changed since it was loaded. Reload before continuing.", "student_id": result.student_id, "current_version": result.version}, status=status.HTTP_409_CONFLICT)
                previous = {"status": result.status, "approved_total": str(result.approved_total) if result.approved_total is not None else None, "approved_grade": result.approved_grade, "approved_calculation": result.approved_calculation}
                if action == "submit":
                    result.status = AssessmentResult.Status.SUBMITTED
                    result.submitted_by = request.user
                    event = ResultAuditEvent.EventType.SUBMITTED
                elif action == "approve":
                    calc = calculate_result(result, persist_approved_snapshot=True)
                    if not calc["complete"] or not calc["grade"]:
                        raise serializers.ValidationError({"calculation": "A complete result and matching grading band are required for approval."})
                    result.status = AssessmentResult.Status.APPROVED
                    result.approved_by = request.user
                    event = ResultAuditEvent.EventType.APPROVED
                else:
                    result.status = AssessmentResult.Status.DRAFT
                    result.reopened_by = request.user
                    event = ResultAuditEvent.EventType.REOPENED
                result.version += 1
                result.save()
                ResultAuditEvent.objects.create(school=plan.school, plan=plan, result=result, actor=request.user, event_type=event, previous_value=previous, new_value={"status": result.status, "approved_calculation": result.approved_calculation if action == "approve" else {}}, reason=reason)
        action_label = {"submit": "submitted", "approve": "approved", "reopen": "reopened"}[action]
        return Response({"detail": f"Results {action_label}.", "results": [AssessmentResultSerializer(AssessmentResult.objects.get(pk=result_by_student[item["student_id"]].pk), context=self.context()).data for item in entries]})


class AssessmentResultDetailView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view"}

    def get(self, request, pk, **kwargs):
        return Response(AssessmentResultSerializer(self.get_result(pk), context=self.context()).data)


class AssessmentResultListView(ResultsMixin, APIView):
    result_permissions = {"GET": "results.view"}

    def get(self, request, **kwargs):
        queryset = AssessmentResult.objects.filter(school=self.school()).select_related(
            "plan", "plan__academic_session", "plan__term", "plan__class_level", "plan__class_arm", "plan__subject", "student", "enrollment",
        ).prefetch_related("scores__plan_component__component", "audit_events__actor")
        allowed_plans = self.plan_queryset().values("id")
        if self.role() == "teacher":
            queryset = queryset.filter(plan_id__in=allowed_plans)
        filters = {
            "academic_session": "plan__academic_session_id", "term": "plan__term_id",
            "class_level": "plan__class_level_id", "class_arm": "plan__class_arm_id",
            "subject": "plan__subject_id", "assessment": "plan_id", "student": "student_id",
            "status": "status",
        }
        for key, lookup in filters.items():
            value = request.query_params.get(key)
            if value:
                if key != "status" and not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                queryset = queryset.filter(**{lookup: value})
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AssessmentResultSerializer(page, many=True, context=self.context()).data)
