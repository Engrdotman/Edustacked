from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership
from apps.schools.tenancy import SchoolScopedQuerySetMixin
from apps.students.models import Student, StudentEnrollment

from .models import AttendanceAuditEvent, AttendanceRecord, AttendanceRegister
from .permissions import HasAttendancePermission
from .serializers import (
    AttendanceRecordSerializer, AttendanceRecordUpdateSerializer,
    AttendanceRegisterCreateSerializer, AttendanceRegisterListSerializer,
    AttendanceRegisterSerializer, BulkAttendanceSerializer,
    EligibleStudentSerializer, RegisterActionSerializer,
)
from .services import (
    eligible_enrollments, local_school_date, scoped_teacher_register_filter,
    teacher_has_register_assignment,
)


class AttendancePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AttendanceViewMixin(SchoolScopedQuerySetMixin):
    permission_classes = (IsAuthenticated, HasAttendancePermission)
    pagination_class = AttendancePagination

    def get_school(self):
        return self.get_authorized_school()

    def get_serializer_context(self):
        return {"request": self.request, "view": self, "format": self.format_kwarg, "school": self.get_school()}

    def role(self):
        if self.request.user.is_superuser:
            return "school_admin"
        return authorized_membership(self.request.user, self.request, self).role

    def can_manage(self):
        return self.request.user.is_superuser or "attendance.manage" in ROLE_PERMISSIONS.get(self.role(), frozenset())


class EligibleStudentsView(AttendanceViewMixin, APIView):
    attendance_permissions = {"GET": "attendance.record"}

    def get(self, request, **kwargs):
        school = self.get_school()
        required = ("academic_session", "class_level", "class_arm", "date")
        if any(not request.query_params.get(key) for key in required):
            raise serializers.ValidationError({"detail": "academic_session, class_level, class_arm, and date are required."})
        ids = {}
        for key in required[:3]:
            value = request.query_params[key]
            if not value.isdecimal():
                raise serializers.ValidationError({key: "Use a valid ID."})
            ids[key] = int(value)
        try:
            attendance_date = date.fromisoformat(request.query_params["date"])
        except ValueError as exc:
            raise serializers.ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        session = get_object_or_404(AcademicSession.objects.filter(school=school), pk=ids["academic_session"])
        class_level = get_object_or_404(ClassLevel.objects.filter(school=school), pk=ids["class_level"])
        class_arm = get_object_or_404(ClassArm.objects.filter(school=school), pk=ids["class_arm"])
        if class_arm.class_level_id != class_level.pk:
            raise serializers.ValidationError({"class_arm": "The selected arm does not belong to the selected class."})
        if attendance_date > local_school_date(school):
            raise serializers.ValidationError({"date": "Future attendance registers are not allowed."})
        if not Term.objects.filter(school=school, academic_session=session, start_date__lte=attendance_date, end_date__gte=attendance_date).exists():
            raise serializers.ValidationError({"date": "The date must fall within a term in the selected session."})
        if self.role() == "teacher":
            from apps.staff.models import TeacherAssignment, TeacherProfile
            permitted = TeacherAssignment.objects.filter(
                school=school, teacher__staff__user=request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", academic_session=session,
                class_level=class_level, class_arm=class_arm,
                status=TeacherAssignment.Status.ACTIVE, start_date__lte=attendance_date,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=attendance_date)).exists()
            if not permitted:
                return Response({"detail": "You are not assigned to this class for the selected date."}, status=status.HTTP_404_NOT_FOUND)
        existing = AttendanceRegister.objects.filter(school=school, class_level=class_level, class_arm=class_arm, attendance_date=attendance_date).first()
        if existing:
            enrollments = existing.records.select_related("student", "enrollment").order_by("student__last_name", "student__first_name")
            data = [{"id": row.student_id, "admission_number": row.student.admission_number,
                     "first_name": row.student.first_name, "middle_name": row.student.middle_name,
                     "last_name": row.student.last_name, "enrollment_id": row.enrollment_id,
                     "attendance_record_id": row.pk, "status": row.status} for row in enrollments]
        else:
            enrollments = eligible_enrollments(school, session, class_level, class_arm, attendance_date)
            data = EligibleStudentSerializer(enrollments, many=True).data
        return Response(data)


class AttendanceOptionsView(AttendanceViewMixin, APIView):
    attendance_permissions = {"GET": "attendance.record"}

    def get(self, request, **kwargs):
        school = self.get_school()
        sessions = AcademicSession.objects.filter(school=school)
        classes = ClassLevel.objects.filter(school=school, is_active=True)
        arms = ClassArm.objects.filter(school=school, is_active=True)
        if self.role() == "teacher":
            from apps.staff.models import TeacherAssignment, TeacherProfile
            assignments = TeacherAssignment.objects.filter(
                school=school, teacher__staff__user=request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", status=TeacherAssignment.Status.ACTIVE,
            )
            on_date = request.query_params.get("date")
            if on_date:
                try:
                    selected_date = date.fromisoformat(on_date)
                except ValueError as exc:
                    raise serializers.ValidationError({"date": "Use YYYY-MM-DD."}) from exc
                assignments = assignments.filter(start_date__lte=selected_date).filter(Q(end_date__isnull=True) | Q(end_date__gte=selected_date))
            session_ids = assignments.values_list("academic_session_id", flat=True).distinct()
            class_ids = assignments.values_list("class_level_id", flat=True).distinct()
            arm_ids = assignments.values_list("class_arm_id", flat=True).distinct()
            sessions = sessions.filter(pk__in=session_ids)
            classes = classes.filter(pk__in=class_ids)
            arms = arms.filter(pk__in=arm_ids)
        class_rows = []
        for level in classes.order_by("name"):
            class_rows.append({"id": level.pk, "name": level.name, "arms": list(arms.filter(class_level=level).order_by("name").values("id", "name"))})
        return Response({
            "sessions": list(sessions.order_by("-start_date").values("id", "name", "start_date", "end_date", "status")),
            "classes": class_rows,
            "terms": list(Term.objects.filter(school=school, academic_session__in=sessions).order_by("academic_session", "sequence").values("id", "name", "academic_session_id", "start_date", "end_date")),
        })


class AttendanceRegisterListView(AttendanceViewMixin, ListAPIView):
    queryset = AttendanceRegister.objects.select_related("academic_session", "term", "class_level", "class_arm", "created_by")
    attendance_permissions = {"GET": "attendance.view"}

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if bool(params.get("date_from")) != bool(params.get("date_to")):
            raise serializers.ValidationError({"date_from": "Provide both date_from and date_to."})
        if params.get("date_from"):
            try:
                date_from, date_to = date.fromisoformat(params["date_from"]), date.fromisoformat(params["date_to"])
            except ValueError as exc:
                raise serializers.ValidationError({"date_from": "Use YYYY-MM-DD dates."}) from exc
            if date_to < date_from or (date_to - date_from).days > 365:
                raise serializers.ValidationError({"date_to": "Date range must be ordered and no longer than 366 days."})
        for key, field in (("academic_session", "academic_session_id"), ("term", "term_id"), ("class_level", "class_level_id"), ("class_arm", "class_arm_id")):
            value = params.get(key)
            if value:
                if not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                queryset = queryset.filter(**{field: int(value)})
        for key, lookup in (("date", "attendance_date"), ("date_from", "attendance_date__gte"), ("date_to", "attendance_date__lte")):
            value = params.get(key)
            if value:
                queryset = queryset.filter(**{lookup: value})
        if params.get("status"):
            if params["status"] not in AttendanceRegister.Status.values:
                raise serializers.ValidationError({"status": "Use draft, submitted, or finalized."})
            queryset = queryset.filter(status=params["status"])
        if self.role() == "teacher":
            queryset = queryset.filter(scoped_teacher_register_filter(self.request.user))
        return queryset.annotate(record_count=Count("records"))

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        return AttendanceRegisterListSerializer


class AttendanceRegisterCreateView(AttendanceViewMixin, APIView):
    attendance_permissions = {"POST": "attendance.record"}

    def post(self, request, **kwargs):
        serializer = AttendanceRegisterCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        if self.role() == "teacher":
            attrs = serializer.validated_data
            candidate = AttendanceRegister(
                school=self.get_school(), created_by=request.user,
                academic_session=attrs["academic_session"], term=attrs["term"],
                class_level=attrs["class_level"], class_arm=attrs["class_arm"],
                attendance_date=attrs["attendance_date"],
            )
            if not teacher_has_register_assignment(request.user, candidate):
                return Response({"detail": "You are not assigned to this class for the selected date."}, status=status.HTTP_404_NOT_FOUND)
        register = serializer.save()
        return Response(AttendanceRegisterSerializer(register, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


class AttendanceRegisterDetailView(AttendanceViewMixin, RetrieveAPIView):
    queryset = AttendanceRegister.objects.select_related("academic_session", "term", "class_level", "class_arm").prefetch_related("records__student", "audit_events__actor")
    attendance_permissions = {"GET": "attendance.view"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.role() == "teacher":
            queryset = queryset.filter(scoped_teacher_register_filter(self.request.user))
        return queryset

    serializer_class = AttendanceRegisterSerializer


def _record_changes(request, register_id, payload, single_record=None):
    # Lock + optimistic version compare ensures concurrent clients cannot silently overwrite a newer register.
    with transaction.atomic():
        register = get_object_or_404(AttendanceRegister.objects.select_for_update(), school=request.attendance_school, pk=register_id)
        if payload["version"] != register.version:
            return None, Response({"detail": "This register changed since it was loaded. Reload before saving.", "current_version": register.version}, status=status.HTTP_409_CONFLICT)
        if register.status == AttendanceRegister.Status.FINALIZED:
            return None, Response({"detail": "Finalized registers must be reopened before correction."}, status=status.HTTP_409_CONFLICT)
        if register.status == AttendanceRegister.Status.SUBMITTED and not request.attendance_can_manage:
            return None, Response({"detail": "Only attendance managers can correct a submitted register."}, status=status.HTTP_403_FORBIDDEN)
        if not request.attendance_can_manage and not teacher_has_register_assignment(request.user, register):
            return None, Response({"detail": "You are not assigned to this register."}, status=status.HTTP_404_NOT_FOUND)
        entries = payload["records"]
        record_ids = [entry["student_id"] for entry in entries]
        rows = register.records.select_for_update().select_related("student", "enrollment").filter(student_id__in=record_ids)
        row_map = {row.student_id: row for row in rows}
        missing = set(record_ids) - set(row_map)
        if missing:
            raise serializers.ValidationError({"records": f"Student IDs are not on this register roster: {', '.join(map(str, sorted(missing)))}."})
        actor = request.user
        for entry in entries:
            record = row_map[entry["student_id"]]
            new_status = entry["status"]
            new_note = entry.get("note", record.note)
            changed = record.status != new_status or record.note != new_note
            if not changed:
                continue
            reason = entry.get("reason", "").strip()
            if record.status is not None and record.status != new_status and not reason:
                raise serializers.ValidationError({"records": f"A correction reason is required for {record.student.admission_number}."})
            previous = record.status or ""
            event_type = AttendanceAuditEvent.EventType.RECORDED if record.status is None else AttendanceAuditEvent.EventType.CORRECTED
            record.status = new_status
            record.note = new_note
            if record.recorded_by_id is None:
                record.recorded_by = actor
            record.last_modified_by = actor
            try:
                record.save()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
            AttendanceAuditEvent.objects.create(
                school=register.school, register=register, record=record, actor=actor,
                event_type=event_type, previous_status=previous, new_status=new_status,
                reason=reason,
            )
        register.version += 1
        register.save(update_fields=("version", "updated_at"))
    return register, None


class AttendanceBulkUpdateView(AttendanceViewMixin, APIView):
    attendance_permissions = {"PATCH": "attendance.record"}

    def patch(self, request, pk, **kwargs):
        serializer = BulkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.attendance_school = self.get_school()
        request.attendance_can_manage = self.can_manage()
        register, error = _record_changes(request, pk, serializer.validated_data)
        if error:
            return error
        return Response(AttendanceRegisterSerializer(register, context=self.get_serializer_context()).data)


class AttendanceRecordListView(AttendanceViewMixin, ListAPIView):
    queryset = AttendanceRecord.objects.select_related("register", "student", "enrollment")
    attendance_permissions = {"GET": "attendance.view"}
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if bool(params.get("date_from")) != bool(params.get("date_to")):
            raise serializers.ValidationError({"date_from": "Provide both date_from and date_to."})
        if params.get("date_from"):
            try:
                date_from, date_to = date.fromisoformat(params["date_from"]), date.fromisoformat(params["date_to"])
            except ValueError as exc:
                raise serializers.ValidationError({"date_from": "Use YYYY-MM-DD dates."}) from exc
            if date_to < date_from or (date_to - date_from).days > 365:
                raise serializers.ValidationError({"date_to": "Date range must be ordered and no longer than 366 days."})
        for key, lookup in (("attendance_date", "register__attendance_date"), ("date_from", "register__attendance_date__gte"), ("date_to", "register__attendance_date__lte"), ("academic_session", "register__academic_session_id"), ("term", "register__term_id"), ("class_level", "register__class_level_id"), ("class_arm", "register__class_arm_id"), ("student", "student_id")):
            value = params.get(key)
            if value:
                if key not in ("attendance_date", "date_from", "date_to") and not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                queryset = queryset.filter(**{lookup: value})
        if params.get("status"):
            if params["status"] not in AttendanceRecord.Status.values:
                raise serializers.ValidationError({"status": "Use present, absent, late, or excused."})
            queryset = queryset.filter(status=params["status"])
        if not params.get("date_from") and not params.get("attendance_date"):
            queryset = queryset.filter(register__attendance_date__gte=local_school_date(self.get_school()) - timedelta(days=30))
        if self.role() == "teacher":
            queryset = queryset.filter(register__in=AttendanceRegister.objects.filter(scoped_teacher_register_filter(self.request.user)))
        if not params.get("include_provisional", "").lower() == "true":
            queryset = queryset.filter(register__status=AttendanceRegister.Status.FINALIZED)
        else:
            queryset = queryset.exclude(register__status=AttendanceRegister.Status.DRAFT)
        return queryset


class AttendanceRecordUpdateView(AttendanceViewMixin, APIView):
    attendance_permissions = {"PATCH": "attendance.record"}

    def patch(self, request, pk, **kwargs):
        record = get_object_or_404(AttendanceRecord.objects.select_related("register"), school=self.get_school(), pk=pk)
        serializer = AttendanceRecordUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request.attendance_school = self.get_school()
        request.attendance_can_manage = self.can_manage()
        payload = {"version": data["version"], "records": [{"student_id": record.student_id, "status": data["status"], "note": data.get("note", record.note), "reason": data.get("reason", "")}]}
        register, error = _record_changes(request, record.register_id, payload)
        if error:
            return error
        updated = register.records.get(pk=record.pk)
        return Response(AttendanceRecordSerializer(updated).data)


class AttendanceRegisterActionView(AttendanceViewMixin, APIView):
    attendance_action_permissions = {"submit": "attendance.record", "finalize": "attendance.manage", "reopen": "attendance.manage"}

    def post(self, request, pk, action, **kwargs):
        school = self.get_school()
        payload = RegisterActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        reason = data.get("reason", "").strip()
        if action == "reopen" and not reason:
            raise serializers.ValidationError({"reason": "A reason is required to reopen a finalized register."})
        with transaction.atomic():
            register = get_object_or_404(AttendanceRegister.objects.select_for_update().filter(school=school), pk=pk)
            if data["version"] != register.version:
                return Response({"detail": "This register changed since it was loaded. Reload before continuing.", "current_version": register.version}, status=status.HTTP_409_CONFLICT)
            if self.role() == "teacher" and not teacher_has_register_assignment(request.user, register):
                return Response({"detail": "You are not assigned to this register."}, status=status.HTTP_404_NOT_FOUND)
            if action == "submit":
                if register.status != AttendanceRegister.Status.DRAFT:
                    return Response({"detail": "Only a draft register can be submitted."}, status=status.HTTP_409_CONFLICT)
                if register.records.filter(status__isnull=True).exists():
                    raise serializers.ValidationError({"records": "Record a status for every eligible student before submitting."})
                register.status = AttendanceRegister.Status.SUBMITTED
                register.submitted_by = request.user
                event = AttendanceAuditEvent.EventType.SUBMITTED
            elif action == "finalize":
                if register.status != AttendanceRegister.Status.SUBMITTED:
                    return Response({"detail": "Only a submitted register can be finalized."}, status=status.HTTP_409_CONFLICT)
                register.status = AttendanceRegister.Status.FINALIZED
                register.finalized_by = request.user
                event = AttendanceAuditEvent.EventType.FINALIZED
            elif action == "reopen":
                if register.status != AttendanceRegister.Status.FINALIZED:
                    return Response({"detail": "Only a finalized register can be reopened."}, status=status.HTTP_409_CONFLICT)
                register.status = AttendanceRegister.Status.SUBMITTED
                register.reopened_by = request.user
                event = AttendanceAuditEvent.EventType.REOPENED
            else:
                return Response({"detail": "Unknown register action."}, status=status.HTTP_404_NOT_FOUND)
            register.version += 1
            try:
                register.save()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
            AttendanceAuditEvent.objects.create(school=school, register=register, actor=request.user, event_type=event, previous_status=AttendanceRegister.Status.SUBMITTED if action == "reopen" else AttendanceRegister.Status.DRAFT if action == "submit" else AttendanceRegister.Status.SUBMITTED, new_status=register.status, reason=reason)
        return Response(AttendanceRegisterSerializer(register, context=self.get_serializer_context()).data)


class StudentAttendanceHistoryView(AttendanceViewMixin, ListAPIView):
    serializer_class = AttendanceRecordSerializer
    pagination_class = AttendancePagination
    attendance_permissions = {"GET": "attendance.view"}

    def get_queryset(self):
        student = get_object_or_404(Student.objects.filter(school=self.get_school()), pk=self.kwargs["student_id"])
        queryset = AttendanceRecord.objects.filter(school=self.get_school(), student=student).select_related("register", "student", "enrollment").exclude(status__isnull=True)
        if self.role() == "teacher":
            from apps.staff.models import TeacherAssignment
            assignments = TeacherAssignment.objects.filter(school=self.get_school(), teacher__staff__user=self.request.user, status=TeacherAssignment.Status.ACTIVE)
            allowed = False
            for assignment in assignments:
                if student.enrollments.filter(academic_session_id=assignment.academic_session_id, class_level_id=assignment.class_level_id, class_arm_id=assignment.class_arm_id, status=StudentEnrollment.Status.ACTIVE).exists():
                    allowed = True
                    break
            if not allowed:
                return queryset.none()
            queryset = queryset.filter(register__in=AttendanceRegister.objects.filter(scoped_teacher_register_filter(self.request.user)))
        params = self.request.query_params
        for key, lookup in (("date_from", "register__attendance_date__gte"), ("date_to", "register__attendance_date__lte"), ("status", "status")):
            if params.get(key):
                queryset = queryset.filter(**{lookup: params[key]})
        if self.request.query_params.get("include_provisional", "").lower() == "true":
            return queryset.exclude(register__status=AttendanceRegister.Status.DRAFT)
        return queryset.filter(register__status=AttendanceRegister.Status.FINALIZED)


class AttendanceReportView(AttendanceViewMixin, APIView):
    attendance_permissions = {"GET": "attendance.view"}

    def get(self, request, **kwargs):
        params = request.query_params
        start, end = params.get("date_from"), params.get("date_to")
        if not start or not end:
            raise serializers.ValidationError({"date_from": "Provide both date_from and date_to (YYYY-MM-DD)."})
        try:
            from_date = date.fromisoformat(start)
            to_date = date.fromisoformat(end)
        except ValueError as exc:
            raise serializers.ValidationError({"date_from": "Use YYYY-MM-DD dates."}) from exc
        if to_date < from_date or (to_date - from_date).days > 365:
            raise serializers.ValidationError({"date_to": "Date range must be ordered and no longer than 366 days."})
        include_provisional = params.get("include_provisional", "").lower() == "true"
        register_statuses = [AttendanceRegister.Status.FINALIZED]
        if include_provisional:
            register_statuses.append(AttendanceRegister.Status.SUBMITTED)
        records = AttendanceRecord.objects.filter(
            school=self.get_school(), register__status__in=register_statuses,
            register__attendance_date__gte=from_date, register__attendance_date__lte=to_date,
        ).exclude(status__isnull=True)
        id_filters = (("academic_session", "register__academic_session_id", AcademicSession), ("term", "register__term_id", Term), ("class_level", "register__class_level_id", ClassLevel), ("class_arm", "register__class_arm_id", ClassArm), ("student", "student_id", Student))
        for key, lookup, model in id_filters:
            value = params.get(key)
            if value:
                if not value.isdecimal():
                    raise serializers.ValidationError({key: "Use a valid ID."})
                if not model.objects.filter(school=self.get_school(), pk=int(value)).exists():
                    raise serializers.ValidationError({key: "Choose a record in this school."})
                records = records.filter(**{lookup: int(value)})
        if self.role() == "teacher":
            records = records.filter(register__in=AttendanceRegister.objects.filter(scoped_teacher_register_filter(request.user)))
        counts = records.aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
            late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
            excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
        )
        denominator = counts["total"] or 0
        counts["attendance_percentage"] = round((counts["present"] + counts["late"]) * 100 / denominator, 2) if denominator else 0.0
        daily = list(records.values("register__attendance_date").annotate(
            total=Count("id"), present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
            late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
            excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
        ).order_by("register__attendance_date"))
        classes = list(records.values("register__class_level_id", "register__class_level__name", "register__class_arm_id", "register__class_arm__name").annotate(
            total=Count("id"), present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
            late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
            excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
        ).order_by("register__class_level__name", "register__class_arm__name"))
        for row in classes:
            row["attendance_percentage"] = round((row["present"] + row["late"]) * 100 / row["total"], 2) if row["total"] else 0.0
        return Response({"from": start, "to": end, "included_register_statuses": register_statuses, "percentage_policy": "present and late count as attended; all recorded statuses including excused count in the denominator; missing or draft registers are excluded", "totals": counts, "daily": daily, "classes": classes})
