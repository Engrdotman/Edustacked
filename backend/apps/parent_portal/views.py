from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.academics.models import AcademicSession
from apps.attendance.models import AttendanceRecord, AttendanceRegister
from apps.attendance.services import finalized_enrollment_summary
from apps.report_cards.models import ReportCardRevision
from apps.report_cards.views import render_report_pdf
from apps.schools.models import School
from apps.schools.permissions import HasSchoolPermission
from apps.schools.tenancy import resolve_authorized_school
from apps.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

from .models import Announcement, GuardianInvitation, PortalAuditEvent, PortalNotification
from .permissions import HasGuardianPortalAccess
from .serializers import (
    AnnouncementParentSerializer, AnnouncementSerializer,
    GuardianActivationSerializer, GuardianProfileSerializer,
    PortalNotificationSerializer,
)
from .services import (
    activate_guardian_invitation, guardian_records_for_user,
    issue_guardian_invitation, linked_student_queryset, schools_for_user,
)


class PortalPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


def linked_student_or_404(user, student_id):
    student = linked_student_queryset(user).select_related("school").filter(pk=student_id).first()
    if student is None:
        PortalAuditEvent.objects.create(actor=user, action="unauthorized_student_access", metadata={"resource": "student"})
        raise Http404
    return student


def latest_enrollment(student):
    current = student.enrollments.filter(
        status=StudentEnrollment.Status.ACTIVE,
        academic_session__status=AcademicSession.Status.ACTIVE,
    ).select_related("academic_session", "class_level", "class_arm").order_by("-academic_session__start_date").first()
    if current:
        return current
    return student.enrollments.exclude(status=StudentEnrollment.Status.PENDING).select_related(
        "academic_session", "class_level", "class_arm"
    ).order_by("-academic_session__start_date", "-enrollment_date").first()


def student_summary(student):
    enrollment = latest_enrollment(student)
    school = student.school
    return {
        "id": student.pk,
        "name": " ".join(part for part in (student.first_name, student.middle_name, student.last_name) if part),
        "admission_number": student.admission_number,
        "school": {"id": school.pk, "name": school.name},
        "enrollment": ({
            "session_id": enrollment.academic_session_id,
            "session_name": enrollment.academic_session.name,
            "class_name": enrollment.class_level.name,
            "arm_name": enrollment.class_arm.name,
            "status": enrollment.status,
        } if enrollment else None),
    }


class GuardianActivationView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, **kwargs):
        serializer = GuardianActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = activate_guardian_invitation(serializer.validated_data["token"], serializer.validated_data["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({"activated": True, "email": user.email, "message": "Portal access is active. Sign in with your email and password."}, status=status.HTTP_200_OK)


class GuardianInvitationCreateView(APIView):
    """Staff invitation for one existing, authorized student-guardian link."""
    from apps.students.permissions import HasStudentPermission
    permission_classes = (IsAuthenticated, HasStudentPermission)
    student_permissions = {"POST": "students.guardians.manage"}

    def post(self, request, student_id, link_id, **kwargs):
        school = resolve_authorized_school(request.user, request.headers.get("X-School-ID"))
        link = get_object_or_404(
            StudentGuardian.objects.select_related("guardian", "student", "school"),
            pk=link_id, student_id=student_id, school=school, is_active=True,
            student__school=school, guardian__is_active=True,
        )
        try:
            issue_guardian_invitation(link, request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({"detail": "A one-time activation link was emailed to the guardian on file."}, status=status.HTTP_202_ACCEPTED)


class GuardianProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, **kwargs):
        if not linked_student_queryset(request.user).exists():
            raise Http404
        return Response(GuardianProfileSerializer(request.user).data)

    def patch(self, request, **kwargs):
        if not linked_student_queryset(request.user).exists():
            raise Http404
        serializer = GuardianProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        PortalAuditEvent.objects.create(actor=user, guardian=guardian_records_for_user(user).first(), action="guardian_profile_updated", metadata={"fields": sorted(serializer.validated_data.keys())})
        return Response(GuardianProfileSerializer(user).data)


class GuardianPortalView(APIView):
    permission_classes = (IsAuthenticated, HasGuardianPortalAccess)


class LinkedStudentListView(GuardianPortalView):
    def get(self, request, **kwargs):
        students = linked_student_queryset(request.user).select_related("school").order_by("school__name", "last_name", "first_name")
        return Response([student_summary(student) for student in students])


class LinkedStudentDetailView(GuardianPortalView):
    def get(self, request, student_id, **kwargs):
        return Response(student_summary(linked_student_or_404(request.user, student_id)))


class GuardianAttendanceView(GuardianPortalView):
    def get(self, request, student_id, **kwargs):
        student = linked_student_or_404(request.user, student_id)
        enrollments = student.enrollments.exclude(status=StudentEnrollment.Status.PENDING).select_related("academic_session")
        session_id = request.query_params.get("session")
        if session_id:
            if not session_id.isdecimal() or not enrollments.filter(academic_session_id=int(session_id)).exists():
                raise serializers.ValidationError({"session": "Choose an academic session belonging to this student."})
            enrollments = enrollments.filter(academic_session_id=int(session_id))
        start = parse_date(request.query_params.get("start_date", "")) if request.query_params.get("start_date") else None
        end = parse_date(request.query_params.get("end_date", "")) if request.query_params.get("end_date") else timezone.localdate()
        if request.query_params.get("start_date") and start is None:
            raise serializers.ValidationError({"start_date": "Use YYYY-MM-DD."})
        if request.query_params.get("end_date") and end is None:
            raise serializers.ValidationError({"end_date": "Use YYYY-MM-DD."})
        if start is None:
            starts = list(enrollments.values_list("enrollment_date", flat=True))
            start = min(starts) if starts else end - timedelta(days=365)
        if start > end:
            raise serializers.ValidationError({"start_date": "Start date must be on or before end date."})
        total = {key: 0 for key in ("total", "present", "absent", "late", "excused", "register_days_with_record")}
        for enrollment in enrollments:
            counts = finalized_enrollment_summary(enrollment, start, end)
            for key in total:
                total[key] += counts[key] or 0
        total["attendance_percentage"] = round((total["present"] + total["late"]) * 100 / total["total"], 2) if total["total"] else None
        total["policy"] = "Finalized registers only. Missing registers and unmarked records are excluded, not counted as absences. Present and late count as attended; absent and excused are included in the denominator."
        records = AttendanceRecord.objects.filter(
            school=student.school, student=student,
            enrollment__in=enrollments,
            register__status=AttendanceRegister.Status.FINALIZED,
            register__attendance_date__gte=start, register__attendance_date__lte=end,
        ).exclude(status__isnull=True).select_related("register__academic_session", "register__term").order_by("-register__attendance_date", "-id")
        paginator = PortalPagination()
        page = paginator.paginate_queryset(records, request)
        rows = [{
            "id": row.pk,
            "date": row.register.attendance_date,
            "status": row.status,
            "session": row.register.academic_session.name,
            "term": row.register.term.name,
        } for row in page]
        paginated = paginator.get_paginated_response(rows)
        return Response({"summary": total, "start_date": start, "end_date": end, **paginated.data})


class GuardianReportCardListView(GuardianPortalView):
    def get(self, request, student_id, **kwargs):
        student = linked_student_or_404(request.user, student_id)
        revisions = ReportCardRevision.objects.filter(
            report_card__student=student,
            report_card__school=student.school,
            status=ReportCardRevision.Status.FINALIZED,
        ).select_related("report_card__academic_session", "report_card__term", "report_card__class_level", "report_card__class_arm").order_by(
            "-report_card__academic_session__start_date", "-report_card__term__sequence", "-revision_number"
        )
        return Response([{
            "id": row.pk,
            "report_card_id": row.report_card_id,
            "identifier": row.report_card.identifier,
            "revision_number": row.revision_number,
            "session": row.report_card.academic_session.name,
            "term": row.report_card.term.name,
            "class_name": row.report_card.class_level.name,
            "arm_name": row.report_card.class_arm.name,
            "finalized_at": row.finalized_at,
        } for row in revisions])


class GuardianReportCardDetailView(GuardianPortalView):
    def get_revision(self, request, revision_id):
        revision = ReportCardRevision.objects.filter(
            pk=revision_id, status=ReportCardRevision.Status.FINALIZED,
            report_card__student__in=linked_student_queryset(request.user),
        ).select_related("report_card", "report_card__student", "report_card__school").first()
        if revision is None:
            PortalAuditEvent.objects.create(actor=request.user, action="unauthorized_report_card_access", metadata={"resource": "published_report_card"})
            raise Http404
        return revision

    def get(self, request, revision_id, **kwargs):
        revision = self.get_revision(request, revision_id)
        snapshot = revision.snapshot or {}
        allowed = {
            "school": {key: snapshot.get("school", {}).get(key) for key in ("name", "address", "contact_phone", "contact_email", "website", "motto", "primary_color")},
            "academic": snapshot.get("academic", {}),
            "student": {key: snapshot.get("student", {}).get(key) for key in ("name", "admission_number", "class_name", "arm_name")},
            "subjects": snapshot.get("subjects", []),
            "attendance": snapshot.get("attendance", {}),
            "remarks": snapshot.get("remarks", {}),
            "signatures": snapshot.get("signatures", {}),
        }
        card = revision.report_card
        return Response({"id": revision.pk, "report_card_id": card.pk, "identifier": card.identifier, "revision_number": revision.revision_number, "finalized_at": revision.finalized_at, "snapshot": allowed})


class GuardianReportCardPdfView(GuardianReportCardDetailView):
    def get(self, request, revision_id, **kwargs):
        revision = self.get_revision(request, revision_id)
        card = revision.report_card
        pdf = render_report_pdf(card, revision, revision.snapshot)
        filename = f"{card.identifier}-{slugify(card.student.last_name) or 'student'}-v{revision.revision_number}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class GuardianAnnouncementListView(GuardianPortalView):
    def get(self, request, **kwargs):
        now = timezone.now()
        schools = schools_for_user(request.user)
        announcements = Announcement.objects.filter(
            school_id__in=schools, status=Announcement.Status.PUBLISHED,
            published_at__lte=now,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).select_related("school")
        paginator = PortalPagination()
        page = paginator.paginate_queryset(announcements, request)
        return paginator.get_paginated_response(AnnouncementParentSerializer(page, many=True).data)


class GuardianNotificationListView(GuardianPortalView):
    def get(self, request, **kwargs):
        students = linked_student_queryset(request.user)
        schools = schools_for_user(request.user)
        notifications = PortalNotification.objects.filter(user=request.user).filter(
            Q(student__in=students) | Q(announcement__school_id__in=schools) | Q(student__isnull=True, announcement__isnull=True)
        )
        paginator = PortalPagination()
        page = paginator.paginate_queryset(notifications, request)
        return paginator.get_paginated_response(PortalNotificationSerializer(page, many=True).data)


class GuardianNotificationReadView(GuardianPortalView):
    def post(self, request, pk, **kwargs):
        students = linked_student_queryset(request.user)
        schools = schools_for_user(request.user)
        notification = PortalNotification.objects.filter(user=request.user, pk=pk).filter(
            Q(student__in=students) | Q(announcement__school_id__in=schools) | Q(student__isnull=True, announcement__isnull=True)
        ).first()
        if notification is None:
            raise Http404
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=("read_at",))
        return Response(PortalNotificationSerializer(notification).data)


class StaffAnnouncementView(APIView):
    permission_classes = (IsAuthenticated, HasSchoolPermission)
    required_school_permission = "announcements.manage"

    def school(self, request):
        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))

    def get(self, request, **kwargs):
        rows = Announcement.objects.filter(school=self.school(request)).order_by("-updated_at")
        return Response(AnnouncementSerializer(rows, many=True).data)

    def post(self, request, pk=None, action=None, **kwargs):
        if action == "publish":
            return self.publish(request, pk, **kwargs)
        if action == "archive":
            return self.archive(request, pk, **kwargs)
        if pk is not None:
            raise Http404
        school = self.school(request)
        serializer = AnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(school=school, created_by=request.user, updated_by=request.user)
        return Response(AnnouncementSerializer(announcement).data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk, **kwargs):
        announcement = get_object_or_404(Announcement, pk=pk, school=self.school(request))
        serializer = AnnouncementSerializer(announcement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(updated_by=request.user)
        return Response(AnnouncementSerializer(announcement).data)

    @transaction.atomic
    def publish(self, request, pk, **kwargs):
        announcement = get_object_or_404(Announcement.objects.select_for_update(), pk=pk, school=self.school(request))
        if announcement.status == Announcement.Status.ARCHIVED:
            raise serializers.ValidationError({"status": "Archived announcements cannot be published again."})
        if announcement.status != Announcement.Status.PUBLISHED:
            announcement.status = Announcement.Status.PUBLISHED
            announcement.published_at = timezone.now()
            announcement.updated_by = request.user
            try:
                announcement.save()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
            from .services import notify_guardians_for_student
            links = StudentGuardian.objects.filter(
                school=announcement.school, is_active=True, can_receive_communications=True,
                guardian__is_active=True, guardian__user__isnull=False,
            ).values_list("student_id", "guardian__user_id").distinct()
            for student_id, user_id in links:
                from .models import PortalNotification
                PortalNotification.objects.get_or_create(
                    user_id=user_id, event_key=f"announcement:{announcement.pk}:published",
                    defaults={"announcement": announcement, "kind": "announcement_published",
                              "title": announcement.title, "message": f"A new announcement is available from {announcement.school.name}."},
                )
        return Response(AnnouncementSerializer(announcement).data)

    @transaction.atomic
    def archive(self, request, pk, **kwargs):
        announcement = get_object_or_404(Announcement.objects.select_for_update(), pk=pk, school=self.school(request))
        announcement.status = Announcement.Status.ARCHIVED
        announcement.archived_at = timezone.now()
        announcement.updated_by = request.user
        announcement.save()
        return Response(AnnouncementSerializer(announcement).data)
