from datetime import date
from html import escape
from io import BytesIO

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership
from apps.schools.tenancy import SchoolScopedQuerySetMixin
from apps.staff.models import TeacherAssignment, TeacherProfile
from apps.students.models import StudentEnrollment

from .models import ReportCard, ReportCardAuditEvent, ReportCardRevision
from .permissions import HasReportCardPermission
from .serializers import (
    GenerateClassReportCardsSerializer, GenerateReportCardSerializer,
    ReportCardActionSerializer, ReportCardFilterSerializer, ReportCardListSerializer,
    ReportCardRemarksSerializer, ReportCardSerializer,
)
from .services import (
    finalize_report_card, generate_report_card, report_enrollments,
    start_correction_revision, validate_revision_ready,
)


class ReportCardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ReportCardViewMixin(SchoolScopedQuerySetMixin):
    permission_classes = (HasReportCardPermission,)
    pagination_class = ReportCardPagination

    def school(self):
        return self.get_authorized_school()

    def role(self):
        if self.request.user.is_superuser:
            return "school_admin"
        return authorized_membership(self.request.user, self.request, self).role

    def context(self):
        return {"request": self.request, "view": self, "school": self.school()}

    def queryset(self):
        queryset = ReportCard.objects.filter(school=self.school()).select_related(
            "student", "enrollment", "academic_session", "term", "class_level", "class_arm",
            "created_by", "reviewed_by", "approved_by", "finalized_by",
        ).prefetch_related("revisions", "audit_events__actor")
        if self.role() == "teacher":
            assignments = TeacherAssignment.objects.filter(
                school=self.school(), teacher__staff__user=self.request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", status=TeacherAssignment.Status.ACTIVE,
            )
            query = Q(pk__in=[])
            rows = assignments.values_list("academic_session_id", "class_level_id", "class_arm_id", "start_date", "end_date")
            for session_id, class_id, arm_id, start, end in rows:
                scope = Q(academic_session_id=session_id, class_level_id=class_id, class_arm_id=arm_id, term__end_date__gte=start)
                if end:
                    scope &= Q(term__start_date__lte=end)
                query |= scope
            queryset = queryset.filter(query)
        return queryset

    def get_card(self, pk):
        return get_object_or_404(self.queryset(), pk=pk)

    def serialized(self, card):
        data = ReportCardSerializer(card, context=self.context()).data
        if self.role() == "teacher" and data.get("current"):
            revision = data["current"]
            assignments = TeacherAssignment.objects.filter(
                school=card.school, teacher__staff__user=self.request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", academic_session=card.academic_session,
                class_level=card.class_level, class_arm=card.class_arm,
                status=TeacherAssignment.Status.ACTIVE, start_date__lte=card.term.end_date,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=card.term.start_date))
            subject_ids = set(assignments.values_list("subject_id", flat=True))
            revision["snapshot"]["subjects"] = [row for row in revision["snapshot"].get("subjects", []) if row.get("subject_id") in subject_ids]
            for version in data.get("revisions", []):
                version["snapshot"]["subjects"] = [row for row in version["snapshot"].get("subjects", []) if row.get("subject_id") in subject_ids]
        return data


class ReportCardListView(ReportCardViewMixin, APIView):
    report_permissions = {"GET": "report_cards.view"}

    def get(self, request, **kwargs):
        serializer = ReportCardFilterSerializer(data=request.query_params, context={"school": self.school()})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = self.queryset()
        for key in ("academic_session", "term", "class_level", "class_arm", "status"):
            if data.get(key):
                queryset = queryset.filter(**{f"{key}_id" if key != "status" else "status": getattr(data[key], "pk", data[key])})
        if data.get("search"):
            value = data["search"].strip()
            queryset = queryset.filter(Q(student__first_name__icontains=value) | Q(student__middle_name__icontains=value) | Q(student__last_name__icontains=value) | Q(student__admission_number__icontains=value) | Q(identifier__icontains=value))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ReportCardListSerializer(page, many=True).data)


class ReportCardGenerateView(ReportCardViewMixin, APIView):
    report_permissions = {"POST": "report_cards.generate"}

    def post(self, request, **kwargs):
        serializer = GenerateReportCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = self.school()
        enrollment = get_object_or_404(StudentEnrollment.objects.select_related("student", "academic_session", "class_level", "class_arm", "school"), school=school, pk=serializer.validated_data["enrollment"])
        term = get_object_or_404(Term.objects.select_related("academic_session"), school=school, pk=serializer.validated_data["term"])
        if term.academic_session_id != enrollment.academic_session_id:
            raise serializers.ValidationError({"term": "The term does not belong to this enrollment session."})
        exists = ReportCard.objects.filter(school=school, student=enrollment.student, enrollment=enrollment, academic_session=enrollment.academic_session, term=term).exists()
        try:
            card, revision, errors = generate_report_card(enrollment, term, request.user)
        except (DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or "Could not generate report card.") from exc
        return Response({"report_card": self.serialized(card), "validation_errors": errors, "actionable": not errors}, status=status.HTTP_200_OK if exists else status.HTTP_201_CREATED)


class ReportCardGenerateClassView(ReportCardViewMixin, APIView):
    report_permissions = {"POST": "report_cards.generate"}

    def post(self, request, **kwargs):
        serializer = GenerateClassReportCardsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = self.school()
        values = serializer.validated_data
        session = get_object_or_404(AcademicSession, school=school, pk=values["academic_session"])
        term = get_object_or_404(Term, school=school, pk=values["term"], academic_session=session)
        level = get_object_or_404(ClassLevel, school=school, pk=values["class_level"])
        arm = get_object_or_404(ClassArm, school=school, pk=values["class_arm"], class_level=level)
        enrollments = report_enrollments(school, session, term, level, arm)
        if self.role() == "teacher":
            raise PermissionDenied("Teachers can view assigned report cards but cannot generate class report cards.")
        results, failures = [], []
        for enrollment in enrollments:
            try:
                card, revision, errors = generate_report_card(enrollment, term, request.user)
                results.append({"student_id": enrollment.student_id, "report_card_id": card.pk, "identifier": card.identifier, "status": card.status, "validation_errors": errors})
            except (DjangoValidationError, IntegrityError) as exc:
                failures.append({"student_id": enrollment.student_id, "admission_number": enrollment.student.admission_number, "errors": getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or ["Generation failed."]})
        return Response({"generated": len(results), "failed": len(failures), "results": results, "failures": failures}, status=status.HTTP_200_OK)


class ReportCardDetailView(ReportCardViewMixin, APIView):
    report_permissions = {"GET": "report_cards.view", "PATCH": "report_cards.review"}

    def get(self, request, pk, **kwargs):
        return Response(self.serialized(self.get_card(pk)))

    def patch(self, request, pk, **kwargs):
        card = self.get_card(pk)
        if card.status not in (ReportCard.Status.DRAFT, ReportCard.Status.REVIEW):
            raise serializers.ValidationError({"status": "Only an unfinalized report card can be updated."})
        if card.status != ReportCard.Status.DRAFT:
            raise serializers.ValidationError({"status": "Return the report card for correction before changing remarks."})
        serializer = ReportCardRemarksSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        revision = card.revisions.get(revision_number=card.current_revision)
        snapshot = dict(revision.snapshot)
        for key in ("teacher", "head_teacher", "conduct", "effort"):
            if key in serializer.validated_data:
                snapshot["remarks"][key] = serializer.validated_data[key]
        for key in ("class_teacher_signature_name", "head_teacher_signature_name"):
            if key in serializer.validated_data:
                signature_key = "class_teacher" if key.startswith("class_teacher") else "head_teacher"
                snapshot["signatures"][signature_key] = serializer.validated_data[key]
        snapshot["signatures"]["signed"] = False
        revision.snapshot = snapshot
        revision.generated_by = request.user
        revision.save(update_fields=("snapshot", "generated_by"))
        ReportCardAuditEvent.objects.create(report_card=card, revision=revision, actor=request.user, action="remarks_updated")
        return Response(self.serialized(card))


class ReportCardActionView(ReportCardViewMixin, APIView):
    report_action_permissions = {
        "review": "report_cards.review", "approve": "report_cards.approve",
        "finalize": "report_cards.finalize", "return": "report_cards.review",
        "correct": "report_cards.finalize",
    }

    def post(self, request, pk, action, **kwargs):
        card = self.get_card(pk)
        serializer = ReportCardActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "").strip()
        with transaction.atomic():
            card = ReportCard.objects.select_for_update().get(pk=card.pk)
            revision = card.revisions.select_for_update().get(revision_number=card.current_revision)
            if action == "review":
                if card.status != ReportCard.Status.DRAFT:
                    raise serializers.ValidationError({"status": "Only a draft can be submitted for review."})
                try:
                    validate_revision_ready(revision, card)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
                revision.status = ReportCardRevision.Status.REVIEW
                revision.reviewed_by = request.user
                revision.reviewed_at = timezone.now()
                card.status = ReportCard.Status.REVIEW
                card.reviewed_by = request.user
                card.reviewed_at = timezone.now()
            elif action == "approve":
                if card.status != ReportCard.Status.REVIEW:
                    raise serializers.ValidationError({"status": "Only a report card ready for review can be approved."})
                try:
                    validate_revision_ready(revision, card)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
                revision.status = ReportCardRevision.Status.APPROVED
                revision.approved_by = request.user
                revision.approved_at = timezone.now()
                card.status = ReportCard.Status.APPROVED
                card.approved_by = request.user
                card.approved_at = timezone.now()
            elif action == "finalize":
                try:
                    card, revision, billing = finalize_report_card(card, request.user, reason)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
                data = self.serialized(card)
                data["billing"] = billing
                return Response(data)
            elif action == "return":
                if card.status not in (ReportCard.Status.REVIEW, ReportCard.Status.APPROVED) or not reason:
                    raise serializers.ValidationError({"reason": "Only an unfinalized reviewed report card can be returned, with a reason."})
                revision.status = ReportCardRevision.Status.RETURNED
                revision.reason = reason
                card.status = ReportCard.Status.DRAFT
                event = "returned_for_correction"
            elif action == "correct":
                try:
                    card, revision = start_correction_revision(card, request.user, reason)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
                return Response(self.serialized(card))
            else:
                return Response({"detail": "Unknown report-card action."}, status=status.HTTP_404_NOT_FOUND)
            revision.save()
            card.save()
            ReportCardAuditEvent.objects.create(report_card=card, revision=revision, actor=request.user, action=action if action != "return" else event, reason=reason)
        return Response(self.serialized(card))


class ReportCardPdfView(ReportCardViewMixin, APIView):
    report_permissions = {"GET": "report_cards.view"}

    def get(self, request, pk, **kwargs):
        card = self.get_card(pk)
        revision_id = request.query_params.get("revision")
        revisions = card.revisions.all()
        if revision_id:
            if not revision_id.isdecimal():
                raise serializers.ValidationError({"revision": "Use a valid revision ID."})
            revision = get_object_or_404(revisions, pk=int(revision_id))
        elif request.query_params.get("preview") == "true":
            revision = revisions.filter(revision_number=card.current_revision).first()
        else:
            revision = revisions.filter(status=ReportCardRevision.Status.FINALIZED).order_by("-revision_number").first()
            if revision is None:
                revision = revisions.filter(revision_number=card.current_revision).first()
        if revision is None:
            raise Http404
        snapshot = revision.snapshot
        if self.role() == "teacher":
            allowed_subjects = set(TeacherAssignment.objects.filter(
                school=card.school, teacher__staff__user=request.user,
                teacher__teaching_status=TeacherProfile.TeachingStatus.ACTIVE,
                teacher__staff__status="active", academic_session=card.academic_session,
                class_level=card.class_level, class_arm=card.class_arm,
                status=TeacherAssignment.Status.ACTIVE, start_date__lte=card.term.end_date,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=card.term.start_date)).values_list("subject_id", flat=True))
            snapshot = dict(snapshot)
            snapshot["subjects"] = [row for row in snapshot.get("subjects", []) if row.get("subject_id") in allowed_subjects]
        pdf = render_report_pdf(card, revision, snapshot)
        filename_name = slugify(card.student.last_name) or "student"
        response = HttpResponse(pdf, content_type="application/pdf")
        disposition = "inline" if request.query_params.get("preview") == "true" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{card.identifier}-{filename_name}-v{revision.revision_number}.pdf"'
        return response


def render_report_pdf(card, revision, snapshot):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=f"Report card {card.identifier}")
    styles = getSampleStyleSheet()
    primary = snapshot.get("school", {}).get("primary_color") or "#285744"
    styles.add(ParagraphStyle(name="SchoolTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor(primary), fontSize=17, leading=21, spaceAfter=4))
    styles.add(ParagraphStyle(name="SubheadingSmall", parent=styles["Heading2"], textColor=colors.HexColor(primary), fontSize=12, leading=15, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="SmallBody", parent=styles["BodyText"], fontSize=8.5, leading=11))
    story = []
    school = snapshot.get("school", {})
    logo_path = school.get("logo_path")
    if logo_path:
        try:
            with default_storage.open(logo_path, "rb") as logo_file:
                logo = Image(BytesIO(logo_file.read()), width=22 * mm, height=22 * mm, kind="proportional")
            story.append(Table([[logo, Paragraph(escape(school.get("name", "School")), styles["SchoolTitle"])]], colWidths=[28 * mm, 145 * mm], style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])))
        except (OSError, ValueError):
            story.append(Paragraph(escape(school.get("name", "School")), styles["SchoolTitle"]))
    else:
        story.append(Paragraph(escape(school.get("name", "School")), styles["SchoolTitle"]))
    contacts = " · ".join(value for value in (school.get("address"), school.get("contact_phone"), school.get("contact_email"), school.get("website")) if value)
    if contacts:
        story.append(Paragraph(escape(contacts), styles["SmallBody"]))
    if school.get("motto"):
        story.append(Paragraph(escape(school["motto"]), styles["SmallBody"]))
    if school.get("description"):
        story.append(Paragraph(escape(school["description"]), styles["SmallBody"]))
    story.append(Spacer(1, 5 * mm))
    academic = snapshot.get("academic", {})
    story.append(Paragraph(f"STUDENT REPORT CARD — {escape(academic.get('session', ''))} · {escape(academic.get('term', ''))}", styles["Heading2"]))
    student = snapshot.get("student", {})
    identity = [
        ["Student", student.get("name", ""), "Admission number", student.get("admission_number", "")],
        ["Class", f"{student.get('class_name', '')} {student.get('arm_name', '')}", "Date of birth", student.get("date_of_birth", "")],
        ["Gender", student.get("gender", ""), "Identifier", card.identifier],
    ]
    story.append(Table(identity, colWidths=[27 * mm, 62 * mm, 33 * mm, 48 * mm], style=TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef4ef")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef4ef")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])))
    story.append(Paragraph("Academic performance", styles["SubheadingSmall"]))
    data = [["Subject", "Assessment component", "Score", "Maximum", "Total", "%", "Grade"]]
    for subject in snapshot.get("subjects", []):
        components = subject.get("components", [])
        for index, component in enumerate(components or [{}]):
            data.append([
                subject.get("subject_name", "") if index == 0 else "",
                component.get("name", "—"), component.get("score") or "—", component.get("max_score", "—"),
                subject.get("total", "—") if index == 0 else "", subject.get("percentage", "—") if index == 0 else "", subject.get("grade", "—") if index == 0 else "",
            ])
    if len(data) == 1:
        data.append(["No approved results", "", "", "", "", "", ""])
    result_table = Table(data, repeatRows=1, colWidths=[31 * mm, 42 * mm, 19 * mm, 20 * mm, 23 * mm, 18 * mm, 18 * mm])
    result_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("LEADING", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f9f6")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(result_table)
    story.append(Paragraph("Attendance (finalized registers only)", styles["SubheadingSmall"]))
    attendance = snapshot.get("attendance", {})
    attendance_row = [["Present", "Absent", "Late", "Excused", "Recorded days", "Attendance %"], [attendance.get("present", 0), attendance.get("absent", 0), attendance.get("late", 0), attendance.get("excused", 0), attendance.get("register_days_with_record", 0), attendance.get("attendance_percentage") or "Not available"]]
    story.append(Table(attendance_row, repeatRows=1, colWidths=[25 * mm, 25 * mm, 25 * mm, 25 * mm, 35 * mm, 41 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4ef")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])))
    story.append(Paragraph("Missing attendance registers are excluded; they are not counted as absences.", styles["SmallBody"]))
    remarks = snapshot.get("remarks", {})
    story.append(Paragraph("Remarks", styles["SubheadingSmall"]))
    for label, key in (("Teacher", "teacher"), ("Head teacher", "head_teacher"), ("Conduct", "conduct"), ("Effort", "effort")):
        story.append(Paragraph(f"<b>{label}:</b> {escape(remarks.get(key) or '—')}", styles["SmallBody"]))
    signatures = snapshot.get("signatures", {})
    story.append(Spacer(1, 10 * mm))
    story.append(Table([[f"Class teacher: {signatures.get('class_teacher') or '________________'}", f"Head teacher: {signatures.get('head_teacher') or '________________'}"], ["", ""]], colWidths=[86 * mm, 86 * mm], style=TableStyle([("LINEBELOW", (0, 1), (0, 1), .6, colors.grey), ("LINEBELOW", (1, 1), (1, 1), .6, colors.grey), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("FONTSIZE", (0, 0), (-1, -1), 8)])))
    if revision.status != ReportCardRevision.Status.FINALIZED:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(f"{revision.status.upper()} — NOT AN OFFICIAL FINALIZED REPORT CARD", ParagraphStyle(name="DraftNotice", parent=styles["BodyText"], alignment=TA_CENTER, textColor=colors.HexColor("#9b3f2e"), fontName="Helvetica-Bold", fontSize=9)))
    doc.build(story)
    return output.getvalue()
