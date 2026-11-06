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
from .ratings import RATING_GROUPS, RATING_LABELS, empty_ratings, merge_ratings
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
        if "ratings" in serializer.validated_data:
            snapshot["ratings"] = merge_ratings(
                snapshot.get("ratings", empty_ratings()),
                serializer.validated_data["ratings"],
            )
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
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=18 * mm,
        title=f"Report card {card.identifier}", author="EDUstacked",
    )
    styles = getSampleStyleSheet()
    school = snapshot.get("school", {})
    primary = school.get("primary_color") or "#285744"
    ink = colors.HexColor("#193629")
    muted = colors.HexColor("#59675e")
    pale = colors.HexColor("#edf3ee")
    styles.add(ParagraphStyle(name="SchoolTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=ink, fontName="Helvetica-Bold", fontSize=18, leading=21, spaceAfter=2))
    styles.add(ParagraphStyle(name="SchoolMeta", parent=styles["BodyText"], alignment=TA_CENTER, textColor=muted, fontSize=7.2, leading=9))
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Heading2"], alignment=TA_CENTER, textColor=colors.white, fontName="Helvetica-Bold", fontSize=10, leading=13))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], textColor=colors.HexColor(primary), fontName="Helvetica-Bold", fontSize=9, leading=11, spaceBefore=5, spaceAfter=3))
    styles.add(ParagraphStyle(name="SmallBody", parent=styles["BodyText"], fontSize=7.5, leading=9.2, textColor=ink))
    styles.add(ParagraphStyle(name="ResultCell", parent=styles["BodyText"], fontSize=6.6, leading=8, textColor=ink))
    styles.add(ParagraphStyle(name="ResultHeader", parent=styles["ResultCell"], fontName="Helvetica-Bold", textColor=colors.white, fontSize=6.5, leading=7.5))
    styles.add(ParagraphStyle(name="MetaLabel", parent=styles["SmallBody"], fontName="Helvetica-Bold", textColor=muted, fontSize=6.5, leading=7.5))
    styles.add(ParagraphStyle(name="MetricValue", parent=styles["SmallBody"], fontName="Helvetica-Bold", fontSize=10, leading=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="MetricLabel", parent=styles["SmallBody"], textColor=muted, fontSize=6.4, leading=7.5, alignment=TA_CENTER))
    story = []

    def para(value, style="SmallBody"):
        return Paragraph(escape(str(value or "-")), styles[style])

    logo_path = school.get("logo_path")
    logo = ""
    if logo_path:
        try:
            with default_storage.open(logo_path, "rb") as logo_file:
                logo = Image(BytesIO(logo_file.read()), width=22 * mm, height=22 * mm, kind="proportional")
        except Exception:
            logo = ""
    contacts = "  |  ".join(value for value in (
        school.get("address"), school.get("contact_phone"), school.get("contact_email"), school.get("website"),
    ) if value)
    school_identity = [para(school.get("name") or "School", "SchoolTitle")]
    if contacts:
        school_identity.append(Paragraph(escape(contacts), styles["SchoolMeta"]))
    if school.get("motto"):
        school_identity.append(Paragraph(f"<i>{escape(school['motto'])}</i>", styles["SchoolMeta"]))
    header = Table([[logo, school_identity]], colWidths=[25 * mm, 161 * mm], hAlign="LEFT")
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor(primary)),
    ]))
    story.append(header)

    academic = snapshot.get("academic", {})
    title_bar = Table([[Paragraph(
        f"{escape(str(academic.get('term', 'TERM')).upper())} REPORT CARD  &nbsp; | &nbsp;  {escape(str(academic.get('session', '')))}",
        styles["ReportTitle"],
    )]], colWidths=[186 * mm], hAlign="LEFT")
    title_bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(primary)), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([title_bar, Spacer(1, 2 * mm)])

    student = snapshot.get("student", {})
    overall = snapshot.get("overall") or {}
    class_position = overall.get("class_position")
    position_text = f"{class_position} of {overall.get('class_position_size')}" if class_position else "Not ranked"
    identity = [
        ["Student", student.get("name", ""), "Admission no.", student.get("admission_number", "")],
        ["Class / arm", f"{student.get('class_name', '')} {student.get('arm_name', '')}", "Session", academic.get("session", "")],
        ["Term", academic.get("term", ""), "Date of birth", student.get("date_of_birth", "")],
        ["Gender", student.get("gender", ""), "Term dates", f"{academic.get('term_start', '')} to {academic.get('term_end', '')}"],
    ]
    identity_cells = [[para(label, "MetaLabel"), para(value), para(label2, "MetaLabel"), para(value2)] for label, value, label2, value2 in identity]
    identity_table = Table(identity_cells, colWidths=[23 * mm, 70 * mm, 24 * mm, 69 * mm], hAlign="LEFT")
    identity_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), pale), ("BACKGROUND", (2, 0), (2, -1), pale),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#ccd8ce")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(identity_table)

    metrics = [
        ("OVERALL TOTAL", f"{overall.get('total', '-')} / {overall.get('maximum', '-')}"),
        ("AVERAGE", f"{overall.get('average_percentage', '-')}%" if overall else "-"),
        ("CLASS POSITION", position_text),
        ("SUBJECTS TAKEN", overall.get("subjects_taken", len(snapshot.get("subjects", [])))),
    ]
    metric_table = Table([[Table([[para(value, "MetricValue")], [para(label, "MetricLabel")]], colWidths=[46.5 * mm]) for label, value in metrics]], colWidths=[46.5 * mm] * 4, hAlign="LEFT")
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale), ("BOX", (0, 0), (-1, -1), .4, colors.HexColor("#ccd8ce")),
        ("INNERGRID", (0, 0), (-1, -1), .4, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([Spacer(1, 2 * mm), metric_table, Paragraph("ACADEMIC PERFORMANCE", styles["SectionTitle"])])
    subject_rows = snapshot.get("subjects", [])
    component_names = []
    for subject in subject_rows:
        for component in subject.get("components", []):
            name = component.get("name") or "Assessment"
            if name not in component_names:
                component_names.append(name)
    component_grid = len(component_names) <= 3
    fixed_widths = [35, 19, 14, 12, 16, 16, 16, 20]
    if component_grid:
        displayed_components = component_names or ["Assessment"]
        component_width = (186 - sum(fixed_widths)) / len(displayed_components)
        column_widths = [fixed_widths[0], *([component_width] * len(displayed_components)), *fixed_widths[1:]]
        headers = ["Subject / teacher", *displayed_components, "Total", "Average", "Grade", "Position", "Highest", "Lowest", "Remark"]
        wrapped_data = [[Paragraph(escape(str(value)), styles["ResultHeader"]) for value in headers]]
        for subject in subject_rows:
            component_lookup = {item.get("name") or "Assessment": item for item in subject.get("components", [])}
            subject_html = escape(str(subject.get("subject_name", "")))
            teacher_parts = [subject.get("teacher_name"), subject.get("teacher_qualification")]
            teacher_line = " · ".join(str(part) for part in teacher_parts if part)
            if teacher_line:
                subject_html += f"<br/><font size='5.6' color='#59675e'>{escape(teacher_line)}</font>"
            cells = [Paragraph(subject_html, styles["ResultCell"])]
            for name in displayed_components:
                component = component_lookup.get(name)
                value = "-" if component is None else component.get("score")
                maximum = "-" if component is None else component.get("max_score")
                cells.append(Paragraph(
                    f"{escape(str(value if value is not None else '-'))} / {escape(str(maximum or '-'))}",
                    styles["ResultCell"],
                ))
            position = f"{subject.get('class_position')} of {subject.get('class_size_with_result')}" if subject.get("class_position") else "-"
            cells.extend(Paragraph(escape(str(value)), styles["ResultCell"]) for value in (
                f"{subject.get('total', '-')} / {subject.get('maximum', '-')}",
                f"{subject.get('percentage', '-')}%", subject.get("grade", "-"), position,
                subject.get("highest_total") or "-", subject.get("lowest_total") or "-",
                subject.get("grade_description", "-"),
            ))
            wrapped_data.append(cells)
    else:
        headers = ["Subject", "Assessment breakdown / subject teacher", "Total", "Average", "Grade", "Position", "Remark", "High / low"]
        wrapped_data = [[Paragraph(escape(value), styles["ResultHeader"]) for value in headers]]
        for subject in subject_rows:
            components = subject.get("components", [])
            component_lines = [
                f"{escape(str(component.get('name') or 'Assessment'))}: "
                f"{escape(str(component.get('score') if component.get('score') is not None else '-'))} / "
                f"{escape(str(component.get('max_score') or '-'))}"
                for component in components
            ]
            if subject.get("teacher_name"):
                teacher_line = f"Teacher: {escape(str(subject['teacher_name']))}"
                if subject.get("teacher_qualification"):
                    teacher_line += f" ({escape(str(subject['teacher_qualification']))})"
                component_lines.append(f"<font color='#59675e'>{teacher_line}</font>")
            breakdown = "<br/>".join(component_lines) or "No component detail"
            high_low = f"{subject.get('highest_total') or '-'} / {subject.get('lowest_total') or '-'}"
            position = f"{subject.get('class_position')} of {subject.get('class_size_with_result')}" if subject.get("class_position") else "-"
            wrapped_data.append([
                Paragraph(escape(str(subject.get("subject_name", ""))), styles["ResultCell"]),
                Paragraph(breakdown, styles["ResultCell"]),
                *[Paragraph(escape(str(value)), styles["ResultCell"]) for value in (
                    f"{subject.get('total', '-')} / {subject.get('maximum', '-')}",
                    f"{subject.get('percentage', '-')}%", subject.get("grade", "-"),
                    position, subject.get("grade_description", "-"), high_low,
                )],
            ])
        column_widths = [31 * mm, 48 * mm, 22 * mm, 17 * mm, 12 * mm, 17 * mm, 17 * mm, 22 * mm]
    if not subject_rows:
        wrapped_data.append([Paragraph("No approved results are available.", styles["ResultCell"])] + [""] * (len(headers) - 1))
    result_table = Table(wrapped_data, repeatRows=1, colWidths=[width * mm for width in column_widths], hAlign="LEFT")
    result_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary)),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f9f6")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(result_table)
    story.append(Paragraph("ATTENDANCE", styles["SectionTitle"]))
    attendance = snapshot.get("attendance", {})
    attendance_row = [["Present", "Absent", "Late", "Excused", "Days recorded", "Attendance"], [attendance.get("present", 0), attendance.get("absent", 0), attendance.get("late", 0), attendance.get("excused", 0), attendance.get("register_days_with_record", 0), f"{attendance['attendance_percentage']}%" if attendance.get("attendance_percentage") is not None else "N/A"]]
    attendance_table = Table(attendance_row, repeatRows=1, colWidths=[27 * mm, 27 * mm, 27 * mm, 27 * mm, 39 * mm, 39 * mm], hAlign="LEFT")
    attendance_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pale), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.extend([attendance_table, Paragraph("Based on finalized registers only; missing registers are not counted as absences.", styles["SchoolMeta"])])

    ratings = merge_ratings(empty_ratings(), snapshot.get("ratings") or {})
    rating_tables = []
    for group, definition in RATING_GROUPS.items():
        group_rows = [
            [Paragraph(escape(definition["label"].upper()), styles["ResultHeader"]), ""],
            [para("Trait", "MetaLabel"), para("Score", "MetaLabel")],
        ]
        group_rows.extend(
            [para(item, "ResultCell"), para(ratings[group].get(item) if ratings[group].get(item) is not None else "—", "ResultCell")]
            for item in definition["items"]
        )
        group_table = Table(group_rows, colWidths=[47 * mm, 13 * mm], hAlign="LEFT")
        group_table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary)),
            ("BACKGROUND", (0, 1), (-1, 1), pale), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c8d6ca")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        rating_tables.append(group_table)
    ratings_table = Table([rating_tables], colWidths=[62 * mm] * 3, hAlign="LEFT")
    ratings_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    rating_key = "Rating scale: " + "  ·  ".join(
        f"{score} = {label}" for score, label in RATING_LABELS.items()
    )
    story.extend([
        Paragraph("PSYCHOMOTOR, BEHAVIOUR AND AFFECTIVE RATINGS", styles["SectionTitle"]),
        ratings_table,
        Paragraph(escape(rating_key), styles["SchoolMeta"]),
    ])

    remarks = snapshot.get("remarks", {})
    story.append(Paragraph("TEACHER AND SCHOOL REMARKS", styles["SectionTitle"]))
    remark_rows = [
        [para("Class teacher", "MetaLabel"), para(remarks.get("teacher") or "No teacher remark recorded."), para("Principal / head teacher", "MetaLabel"), para(remarks.get("head_teacher") or "No principal remark recorded.")],
        [para("Conduct", "MetaLabel"), para(remarks.get("conduct") or "Not recorded"), para("Effort", "MetaLabel"), para(remarks.get("effort") or "Not recorded")],
    ]
    remarks_table = Table(remark_rows, colWidths=[25 * mm, 67 * mm, 27 * mm, 68 * mm], hAlign="LEFT")
    remarks_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), pale), ("BACKGROUND", (2, 0), (2, -1), pale), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#c8d6ca")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(remarks_table)

    signatures = snapshot.get("signatures", {})
    story.append(Spacer(1, 4 * mm))
    principal_sign = ""
    signature_path = school.get("principal_signature_path")
    if revision.status == ReportCardRevision.Status.FINALIZED and signature_path:
        try:
            with default_storage.open(signature_path, "rb") as signature_file:
                principal_sign = Image(BytesIO(signature_file.read()), width=42 * mm, height=14 * mm, kind="proportional")
        except Exception:
            principal_sign = ""
    signature_table = Table([
        [para("CLASS TEACHER", "MetaLabel"), para("PRINCIPAL", "MetaLabel")],
        [para(signatures.get("class_teacher") or ""), para(signatures.get("head_teacher") or "")],
        ["____________________________", principal_sign or "____________________________"],
        [para("Date: ____________________", "MetaLabel"), para("Date: ____________________", "MetaLabel")],
    ], colWidths=[93 * mm, 93 * mm], hAlign="LEFT")
    signature_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pale), ("LINEBELOW", (0, 2), (-1, 2), .6, colors.grey), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (0, 0), (-1, -1), "LEFT"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    story.append(signature_table)
    if revision.status != ReportCardRevision.Status.FINALIZED:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(f"{revision.status.upper()} - NOT AN OFFICIAL FINALIZED REPORT CARD", ParagraphStyle(name="DraftNotice", parent=styles["BodyText"], alignment=TA_CENTER, textColor=colors.HexColor("#9b3f2e"), fontName="Helvetica-Bold", fontSize=9)))

    def branded_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d5dfd7"))
        canvas.setLineWidth(.5)
        canvas.line(document.leftMargin, 13 * mm, A4[0] - document.rightMargin, 13 * mm)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(A4[0] / 2, 8.5 * mm, "Powered by EDUstacked  |  edustackedng@gmail.com")
        canvas.drawRightString(A4[0] - document.rightMargin, 8.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=branded_footer, onLaterPages=branded_footer)
    return output.getvalue()
