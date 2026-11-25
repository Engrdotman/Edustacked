import hashlib
import hmac
import json
from collections import defaultdict
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus import Image as ReportImage
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Term
from apps.parent_portal.permissions import HasGuardianPortalAccess
from apps.parent_portal.services import linked_student_queryset
from apps.schools.permissions import ROLE_PERMISSIONS, school_allows_capability, authorized_membership
from apps.schools.tenancy import resolve_authorized_school
from apps.students.models import Guardian, Student, StudentGuardian, StudentEnrollment

from .models import (
    FeeCharge, FeeLedgerEntry, FeeNotification, FeePaymentAllocation, FeeSchedule,
    PaymentProviderEvent, SchoolFeePayment, SchoolFeeSettings,
)
from .providers import provider_for
from .services import (
    charge_balance, confirm_online_payment, issue_fee_schedule, payment_amount_for_guardian, record_physical_payment,
    resend_receipt_otp, reverse_payment, student_fee_summary, verify_receipt_otp,
)


class FeePermission(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True
        required = getattr(view, "fee_permissions", {}).get(request.method)
        if not required:
            return False
        try:
            membership = authorized_membership(request.user, request, view)
        except Http404:
            return False
        return required in ROLE_PERMISSIONS.get(membership.role, frozenset()) and school_allows_capability(membership.school, required)


class SchoolFeeView(APIView):
    permission_classes = (FeePermission,)
    fee_permissions = {}

    def school(self, request):
        return resolve_authorized_school(request.user, request.headers.get("X-School-ID"))


def public_schedule(row):
    return {
        "id": row.pk, "academic_session": row.academic_session_id, "session_name": row.academic_session.name,
        "term": row.term_id, "term_name": row.term.name, "class_level": row.class_level_id,
        "class_name": row.class_level.name, "class_arm": row.class_arm_id,
        "arm_name": row.class_arm.name if row.class_arm_id else "All arms", "category": row.category,
        "description": row.description, "amount_minor": row.amount_minor, "currency": row.currency,
        "due_date": row.due_date, "status": row.status, "created_at": row.created_at,
    }


def public_charge(row, balance_minor=None):
    balance = charge_balance(row) if balance_minor is None else max(0, int(balance_minor or 0))
    return {
        "id": row.pk, "student_id": row.student_id, "student_name": " ".join(filter(None, [row.student.first_name, row.student.middle_name, row.student.last_name])),
        "admission_number": row.student.admission_number, "session_id": row.fee_schedule.academic_session_id,
        "session_name": row.fee_schedule.academic_session.name, "term_id": row.fee_schedule.term_id,
        "term_name": row.fee_schedule.term.name, "class_name": row.enrollment.class_level.name,
        "arm_name": row.enrollment.class_arm.name, "category": row.fee_schedule.category,
        "amount_minor": row.amount_minor, "paid_minor": max(0, row.amount_minor - balance),
        "outstanding_minor": balance, "due_date": row.fee_schedule.due_date,
    }


class FeePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def public_payment(payment, *, include_provider=False, student_ids=None):
    allocation_rows = payment.allocations.select_related("student", "fee_charge__fee_schedule__term", "fee_charge__fee_schedule__academic_session")
    if student_ids is not None:
        allocation_rows = allocation_rows.filter(student_id__in=student_ids)
    allocations = [{
        "student_id": row.student_id,
        "student_name": " ".join(filter(None, [row.student.first_name, row.student.middle_name, row.student.last_name])),
        "admission_number": row.student.admission_number,
        "charge_id": row.fee_charge_id,
        "category": row.fee_charge.fee_schedule.category if row.fee_charge_id else "Unapplied credit",
        "session_name": row.fee_charge.fee_schedule.academic_session.name if row.fee_charge_id else "",
        "term_name": row.fee_charge.fee_schedule.term.name if row.fee_charge_id else "",
        "amount_minor": row.amount_minor,
    } for row in allocation_rows]
    data = {
        "reference": payment.reference, "channel": payment.channel, "method": payment.method,
        "status": payment.status,
        "amount_minor": sum(row["amount_minor"] for row in allocations) if student_ids is not None and allocations else payment.amount_minor,
        "currency": payment.currency,
        "description": payment.description, "payer_email": payment.payer_email,
        "received_at": payment.received_at, "created_at": payment.created_at,
        "allocations": allocations,
    }
    if payment.authorization_url:
        data["authorization_url"] = payment.authorization_url
    if include_provider:
        data["provider"] = payment.provider
    return data


class SchoolFeeSettingsView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view", "PATCH": "fees.settings"}

    def get(self, request, **kwargs):
        school = self.school(request)
        row, _ = SchoolFeeSettings.objects.get_or_create(school=school)
        return Response({
            "bank_name": row.bank_name, "account_name": row.account_name,
            "account_number": row.masked_account_number, "account_type": row.account_type,
            "account_status": row.account_status, "account_verified_name": row.account_verified_name,
            "provider": row.provider, "online_enabled": row.online_enabled,
            "allow_excess_credit": row.allow_excess_credit,
            "allowed_channels": row.allowed_channels,
            "sms_status": "configured" if settings.TERMII_API_KEY and settings.TERMII_SENDER_ID else "not_configured",
        })

    def patch(self, request, **kwargs):
        school = self.school(request)
        row, _ = SchoolFeeSettings.objects.get_or_create(school=school)
        if "online_enabled" in request.data:
            row.online_enabled = bool(request.data["online_enabled"])
        if "allow_excess_credit" in request.data:
            row.allow_excess_credit = bool(request.data["allow_excess_credit"])
        if "allowed_channels" in request.data:
            channels = request.data["allowed_channels"]
            if not isinstance(channels, list) or any(value not in {"card", "bank_transfer", "ussd"} for value in channels):
                raise serializers.ValidationError({"allowed_channels": "Choose card, bank transfer, or USSD payment channels."})
            row.allowed_channels = channels
        try:
            row.save()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return self.get(request)


class BankListView(SchoolFeeView):
    fee_permissions = {"GET": "fees.settings"}

    def get(self, request, **kwargs):
        self.school(request)
        name = request.query_params.get("provider", "")
        try:
            data = provider_for(name).banks()
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        banks = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        return Response([{"code": item.get("code") or item.get("id"), "name": item.get("name") or item.get("bank_name")} for item in banks if isinstance(item, dict)])


class ConnectPaymentAccountView(SchoolFeeView):
    fee_permissions = {"POST": "fees.settings"}

    def post(self, request, **kwargs):
        school = self.school(request)
        provider_name = str(request.data.get("provider", ""))
        bank_code = str(request.data.get("bank_code", "")).strip()
        bank_name = str(request.data.get("bank_name", "")).strip()
        account_number = str(request.data.get("account_number", "")).strip()
        account_type = str(request.data.get("account_type", "")).strip()
        phone = str(request.data.get("business_mobile", "") or school.contact_phone or "").strip()
        if not bank_code or not account_number.isdigit() or len(account_number) < 10 or len(account_number) > 12:
            raise serializers.ValidationError({"account_number": "Enter a valid Nigerian bank account number and select its bank."})
        if not bank_name:
            raise serializers.ValidationError({"bank_name": "Select the bank for this account."})
        try:
            provider = provider_for(provider_name)
            connected = provider.connect_account(
                bank_code=bank_code, account_number=account_number,
                business_name=school.name, phone=phone,
                business_email=school.contact_email,
            )
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        row, _ = SchoolFeeSettings.objects.get_or_create(school=school)
        row.bank_name = bank_name[:120]
        row.bank_code = bank_code[:20]
        # The provider subaccount holds the verified full destination. EDUstacked
        # only needs the last four digits for display, so avoid retaining the full
        # school account number in our database.
        row.account_number = account_number[-4:]
        row.account_type = account_type[:20]
        row.account_name = connected["account_name"][:200]
        row.account_verified_name = connected["account_name"][:200]
        row.account_status = SchoolFeeSettings.AccountStatus.VERIFIED
        row.account_verified_at = timezone.now()
        row.provider = provider_name
        row.provider_account_id = connected["provider_account_id"]
        row.online_enabled = True
        try:
            row.save()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({"detail": f"Bank account verified and connected with {provider_name.title()}. Online school-fee payments are enabled.", "settings": SchoolFeeSettingsView().get(request).data}, status=status.HTTP_200_OK)


class FeeScheduleListCreateView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view", "POST": "fees.manage"}

    def get(self, request, **kwargs):
        school = self.school(request)
        rows = FeeSchedule.objects.filter(school=school).select_related("academic_session", "term", "class_level", "class_arm")
        session_id, term_id, class_id = (request.query_params.get(key) for key in ("session", "term", "class_level"))
        if session_id:
            rows = rows.filter(academic_session_id=session_id)
        if term_id:
            rows = rows.filter(term_id=term_id)
        if class_id:
            rows = rows.filter(class_level_id=class_id)
        return Response([public_schedule(row) for row in rows])

    def post(self, request, **kwargs):
        school = self.school(request)
        data = request.data
        required = ("academic_session", "term", "class_level", "category", "amount_minor")
        if any(not data.get(key) for key in required):
            raise serializers.ValidationError({"detail": "Choose a session, term, class, fee category, and amount."})
        try:
            amount = int(data["amount_minor"])
        except (TypeError, ValueError):
            raise serializers.ValidationError({"amount_minor": "Enter a valid amount in naira."}) from None
        if amount <= 0:
            raise serializers.ValidationError({"amount_minor": "Fee amount must be greater than zero."})
        session = get_object_or_404(AcademicSession, pk=data["academic_session"], school=school)
        term = get_object_or_404(Term, pk=data["term"], school=school, academic_session=session)
        class_level = get_object_or_404(ClassLevel, pk=data["class_level"], school=school)
        class_arm = None
        if data.get("class_arm"):
            class_arm = get_object_or_404(ClassArm, pk=data["class_arm"], school=school, class_level=class_level)
        schedule = FeeSchedule(
            school=school, academic_session=session, term=term, class_level=class_level, class_arm=class_arm,
            category=str(data["category"])[:100], description=str(data.get("description", ""))[:300],
            amount_minor=amount, due_date=data.get("due_date") or None, status=data.get("status", FeeSchedule.Status.ACTIVE), created_by=request.user,
        )
        try:
            with transaction.atomic():
                schedule.save()
                issued = issue_fee_schedule(schedule, request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        schedule.refresh_from_db()
        result = public_schedule(schedule)
        result["issued_students"] = issued
        result["message"] = f"Fee schedule saved and issued to {issued} currently enrolled student(s)."
        return Response(result, status=status.HTTP_201_CREATED)


class FeeScheduleDetailView(SchoolFeeView):
    fee_permissions = {"PATCH": "fees.manage"}

    def patch(self, request, pk, **kwargs):
        school = self.school(request)
        row = get_object_or_404(FeeSchedule.objects.select_related("academic_session", "term", "class_level", "class_arm"), pk=pk, school=school)
        if row.charges.exists():
            if set(request.data.keys()) - {"status"}:
                raise serializers.ValidationError({"detail": "A fee schedule cannot be edited after it has been issued. Deactivate it and create a corrected schedule; existing payment history will remain intact."})
        if "status" in request.data:
            if request.data["status"] not in FeeSchedule.Status.values:
                raise serializers.ValidationError({"status": "Choose active or inactive."})
            row.status = request.data["status"]
            row.save(update_fields=["status", "updated_at"])
        return Response(public_schedule(row))


class FeeChargeListView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view"}

    def get(self, request, **kwargs):
        school = self.school(request)
        rows = FeeCharge.objects.filter(school=school).select_related("student", "enrollment__class_level", "enrollment__class_arm", "fee_schedule__academic_session", "fee_schedule__term").annotate(ledger_balance=Coalesce(Sum("ledger_entries__amount_minor"), Value(0)))
        params = request.query_params
        for key, field in (("student", "student_id"), ("session", "fee_schedule__academic_session_id"), ("term", "fee_schedule__term_id"), ("class_level", "enrollment__class_level_id"), ("class_arm", "enrollment__class_arm_id")):
            if params.get(key):
                rows = rows.filter(**{field: params[key]})
        status_filter = params.get("status")
        search = params.get("search", "").strip().lower()
        if search:
            rows = rows.filter(Q(student__first_name__icontains=search) | Q(student__middle_name__icontains=search) | Q(student__last_name__icontains=search) | Q(student__admission_number__icontains=search) | Q(fee_schedule__category__icontains=search))
        if status_filter == "paid":
            rows = rows.filter(ledger_balance__lte=0)
        elif status_filter == "partial":
            rows = rows.filter(ledger_balance__gt=0, ledger_balance__lt=F("amount_minor"))
        elif status_filter == "unpaid":
            rows = rows.filter(ledger_balance__gte=F("amount_minor"))
        paginator = FeePagination()
        page = paginator.paginate_queryset(rows.order_by("student__last_name", "student__first_name", "fee_schedule__category"), request)
        out = []
        for row in page:
            item = public_charge(row, row.ledger_balance)
            state = "paid" if item["outstanding_minor"] <= 0 else "partial" if item["paid_minor"] else "unpaid"
            out.append({**item, "payment_status": state})
        return paginator.get_paginated_response(out)


class FeeIssueView(SchoolFeeView):
    fee_permissions = {"POST": "fees.manage"}

    def post(self, request, **kwargs):
        school = self.school(request)
        schedule = get_object_or_404(FeeSchedule, pk=request.data.get("schedule_id"), school=school)
        try:
            issued = issue_fee_schedule(schedule, request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({"issued_students": issued, "message": f"{issued} new fee charge(s) were issued to enrolled students."})


class FinanceOverviewView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view"}

    def get(self, request, **kwargs):
        school = self.school(request)
        charges = FeeCharge.objects.filter(school=school)
        params = request.query_params
        mapping = {"session": "fee_schedule__academic_session_id", "term": "fee_schedule__term_id", "class_level": "enrollment__class_level_id", "class_arm": "enrollment__class_arm_id"}
        for key, charge_field in mapping.items():
            if params.get(key):
                charges = charges.filter(**{charge_field: params[key]})
        expected = int(charges.aggregate(total=Sum("amount_minor"))["total"] or 0)
        charge_scope = charges.values("id")
        ledger = FeeLedgerEntry.objects.filter(school=school, fee_charge_id__in=charge_scope)
        collected = int(ledger.filter(kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor__lt=0).aggregate(total=Sum("amount_minor"))["total"] or 0) * -1
        refunded = int(ledger.filter(kind=FeeLedgerEntry.Kind.REFUND, amount_minor__gt=0).aggregate(total=Sum("amount_minor"))["total"] or 0)
        student_expected = {row["student_id"]: int(row["expected"] or 0) for row in charges.values("student_id").annotate(expected=Sum("amount_minor"))}
        student_outstanding = {row["student_id"]: max(0, int(row["balance"] or 0)) for row in ledger.values("student_id").annotate(balance=Sum("amount_minor"))}
        partial = sum(1 for sid, value in student_outstanding.items() if 0 < value < student_expected[sid])
        outstanding_students = sum(1 for value in student_outstanding.values() if value > 0)
        online = int(ledger.filter(payment__channel=SchoolFeePayment.Channel.ONLINE, kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor__lt=0).aggregate(total=Sum("amount_minor"))["total"] or 0) * -1
        physical = int(ledger.filter(payment__channel=SchoolFeePayment.Channel.PHYSICAL, kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor__lt=0).aggregate(total=Sum("amount_minor"))["total"] or 0) * -1
        online_refunds = int(ledger.filter(payment__channel=SchoolFeePayment.Channel.ONLINE, kind=FeeLedgerEntry.Kind.REFUND).aggregate(total=Sum("amount_minor"))["total"] or 0)
        physical_refunds = int(ledger.filter(payment__channel=SchoolFeePayment.Channel.PHYSICAL, kind=FeeLedgerEntry.Kind.REFUND).aggregate(total=Sum("amount_minor"))["total"] or 0)
        return Response({
            "expected_minor": expected, "collected_minor": max(0, collected - refunded), "outstanding_minor": max(0, expected - collected + refunded),
            "physical_minor": max(0, physical - physical_refunds), "online_minor": max(0, online - online_refunds),
            "fully_paid_students": sum(1 for sid, total in student_expected.items() if total > 0 and student_outstanding.get(sid, 0) == 0),
            "partially_paid_students": partial, "students_with_balance": outstanding_students,
            "students_with_fees": len(student_expected),
        })


class SchoolPaymentListView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view"}

    def get(self, request, **kwargs):
        school = self.school(request)
        rows = SchoolFeePayment.objects.filter(school=school).prefetch_related("allocations__student", "allocations__fee_charge__fee_schedule__term", "allocations__fee_charge__fee_schedule__academic_session")
        params = request.query_params
        for key, field in (("status", "status"), ("channel", "channel"), ("method", "method")):
            if params.get(key):
                rows = rows.filter(**{field: params[key]})
        if params.get("date_from"):
            rows = rows.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            rows = rows.filter(created_at__date__lte=params["date_to"])
        if params.get("session"):
            rows = rows.filter(allocations__fee_charge__fee_schedule__academic_session_id=params["session"])
        if params.get("term"):
            rows = rows.filter(allocations__fee_charge__fee_schedule__term_id=params["term"])
        if params.get("class_level"):
            rows = rows.filter(allocations__fee_charge__enrollment__class_level_id=params["class_level"])
        search = params.get("search", "").strip()
        if search:
            rows = rows.filter(Q(reference__icontains=search) | Q(allocations__student__admission_number__icontains=search) | Q(allocations__student__first_name__icontains=search) | Q(allocations__student__last_name__icontains=search))
        paginator = FeePagination()
        page = paginator.paginate_queryset(rows.distinct(), request)
        return paginator.get_paginated_response([public_payment(row, include_provider=True) for row in page])


class ManualPaymentView(SchoolFeeView):
    fee_permissions = {"POST": "fees.record"}

    def post(self, request, **kwargs):
        school = self.school(request)
        try:
            payment = record_physical_payment(
                school=school, actor=request.user,
                amount_minor=request.data.get("amount_minor"), method=request.data.get("method", "cash"),
                allocations=request.data.get("allocations", []), description=str(request.data.get("description", "")),
                payer_email=str(request.data.get("payer_email", "")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({**public_payment(payment), "detail": "Payment recorded. Guardian SMS notifications will be sent when Termii is configured and available."}, status=status.HTTP_201_CREATED)


class PaymentReverseView(SchoolFeeView):
    fee_permissions = {"POST": "fees.manage"}

    def post(self, request, reference, **kwargs):
        school = self.school(request)
        payment = get_object_or_404(SchoolFeePayment, school=school, reference=reference)
        external_reference = str(request.data.get("external_reference", "")).strip()
        if payment.channel == SchoolFeePayment.Channel.ONLINE and not external_reference:
            raise serializers.ValidationError({"external_reference": "Complete the refund with the payment provider first, then enter its refund reference."})
        try:
            reversal = reverse_payment(payment=payment, amount_minor=request.data.get("amount_minor"), reason=str(request.data.get("reason", "")), actor=request.user, external_reference=external_reference)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError({"external_reference": "This refund reference has already been recorded."}) from exc
        payment.refresh_from_db()
        return Response({"detail": "The reversal was recorded in the audit ledger.", "reversal_id": reversal.pk, "status": payment.status})


def receipt_pdf(payment, *, student_ids=None):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=17 * mm, bottomMargin=18 * mm, title=f"Fee receipt {payment.reference}", author="EDUstacked")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("FeeTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#203c2c"), spaceAfter=4)
    logo = None
    if payment.school.logo:
        try:
            payment.school.logo.open("rb")
            logo = ReportImage(BytesIO(payment.school.logo.read()), width=18 * mm, height=18 * mm, kind="proportional")
        except Exception:
            logo = None
        finally:
            try: payment.school.logo.close()
            except Exception: pass
    elements = []
    if logo:
        elements.append(Table([[logo, Paragraph(escape(payment.school.name), title)]], colWidths=[24 * mm, 145 * mm], style=TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ALIGN", (0,0), (0,0), "LEFT"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)])))
    else:
        elements.append(Paragraph(escape(payment.school.name), title))
    elements.extend([Paragraph("SCHOOL FEES PAYMENT RECEIPT", ParagraphStyle("FeeSub", parent=styles["Heading2"], alignment=TA_CENTER, textColor=colors.HexColor("#138eac")))])
    school_details = " · ".join(value for value in [payment.school.address, payment.school.contact_phone, payment.school.contact_email] if value)
    if school_details:
        elements.append(Paragraph(escape(school_details), ParagraphStyle("SchoolContact", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=9, leading=12)))
    elements.append(Spacer(1, 8 * mm))
    elements += [Paragraph(f"Receipt reference: <b>{escape(payment.reference)}</b>", styles["BodyText"]), Paragraph(f"Payment date: {timezone.localtime(payment.received_at or payment.created_at):%d %B %Y, %I:%M %p}", styles["BodyText"]), Spacer(1, 4 * mm)]
    data = [["Student", "Admission no.", "Class", "Session / term", "Fee category", "Previous due", "Received", "Balance"]]
    cell_style = ParagraphStyle("FeeCell", parent=styles["BodyText"], fontSize=7.4, leading=9)
    allocation_rows = payment.allocations.select_related("student", "fee_charge__fee_schedule__academic_session", "fee_charge__fee_schedule__term")
    if student_ids is not None:
        allocation_rows = allocation_rows.filter(student_id__in=student_ids)
    visible_amount_minor = 0
    for allocation in allocation_rows:
        visible_amount_minor += allocation.amount_minor
        student = allocation.student
        schedule = allocation.fee_charge.fee_schedule if allocation.fee_charge_id else None
        data.append([
            Paragraph(escape(" ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))), cell_style),
            Paragraph(escape(student.admission_number), cell_style),
            Paragraph(escape(f"{allocation.fee_charge.enrollment.class_level.name} {allocation.fee_charge.enrollment.class_arm.name}" if allocation.fee_charge_id else "—"), cell_style),
            Paragraph(escape(f"{schedule.academic_session.name} / {schedule.term.name}" if schedule else "—"), cell_style),
            Paragraph(escape(schedule.category if schedule else "Excess payment credit"), cell_style),
            f"NGN {allocation.balance_before_minor / 100:,.2f}" if allocation.balance_before_minor is not None else "—",
            f"NGN {allocation.amount_minor / 100:,.2f}",
            f"NGN {allocation.balance_after_minor / 100:,.2f}" if allocation.balance_after_minor is not None else "—",
        ])
    table = Table(data, colWidths=[25 * mm, 20 * mm, 20 * mm, 23 * mm, 22 * mm, 21 * mm, 21 * mm, 22 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#454b70")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#d8dfdb")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 8), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f1f6f3")]), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    elements.extend([table, Spacer(1, 7 * mm), Paragraph(f"Total received: <b>NGN {visible_amount_minor / 100:,.2f}</b>", styles["Heading3"]), Paragraph(f"Payment method: {payment.get_method_display()} · {payment.get_channel_display()}", styles["BodyText"]), Paragraph(f"Recorded by: {payment.recorded_by.get_full_name() or payment.recorded_by.email}" if payment.recorded_by_id else "Recorded by: Online checkout", styles["BodyText"]), Spacer(1, 8 * mm), Paragraph("This receipt confirms the recorded payment. For help, contact the school office.", styles["BodyText"]), Spacer(1, 15 * mm), Paragraph("Powered by EDUstacked · edustackedng@gmail.com", ParagraphStyle("Footer", parent=styles["BodyText"], alignment=TA_CENTER, textColor=colors.HexColor("#52705c")))])
    doc.build(elements)
    return output.getvalue()


class SchoolReceiptView(SchoolFeeView):
    fee_permissions = {"GET": "fees.view"}

    def get(self, request, reference, **kwargs):
        school = self.school(request)
        payment = get_object_or_404(SchoolFeePayment, school=school, reference=reference, status__in=[SchoolFeePayment.Status.SUCCESS, SchoolFeePayment.Status.PARTIALLY_REVERSED, SchoolFeePayment.Status.REVERSED])
        response = HttpResponse(receipt_pdf(payment), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="fee-receipt-{payment.reference}.pdf"'
        return response


class FeeNotificationRetryView(SchoolFeeView):
    fee_permissions = {"POST": "fees.manage"}

    def post(self, request, pk, **kwargs):
        school = self.school(request)
        notification = get_object_or_404(FeeNotification.objects.select_related("payment", "guardian"), pk=pk, school=school)
        if not notification.guardian or notification.guardian.phone != notification.phone:
            raise serializers.ValidationError({"detail": "This notification no longer has a valid guardian contact. Update the guardian record first."})
        from .services import send_fee_sms
        if notification.kind == FeeNotification.Kind.RECEIPT_OTP:
            raise serializers.ValidationError({"detail": "Use the guardian receipt-code resend flow to issue a fresh, expiring code."})
        amount_minor = payment_amount_for_guardian(notification.payment, notification.guardian)
        if not amount_minor:
            raise serializers.ValidationError({"detail": "This guardian has no payment allocation for this receipt."})
        send_fee_sms(school=school, payment=notification.payment, guardian=notification.guardian, kind=notification.kind,
                     message=f"{school.name}: We recorded NGN {amount_minor / 100:,.2f} for school fees. Receipt {notification.payment.reference}.")
        notification.refresh_from_db()
        return Response({"detail": "The SMS notification retry has been recorded.", "status": notification.status})


class ParentFeeView(APIView):
    permission_classes = (IsAuthenticated, HasGuardianPortalAccess)

    def linked_student(self, request, student_id):
        student = linked_student_queryset(request.user).filter(pk=student_id).select_related("school").first()
        if student is None:
            raise Http404
        return student

    def guardian_for_student(self, request, student):
        return Guardian.objects.filter(user=request.user, school=student.school, student_links__student=student, student_links__is_active=True, student_links__can_receive_communications=True).distinct().first()


class ParentStudentFeesView(ParentFeeView):
    def get(self, request, student_id, **kwargs):
        student = self.linked_student(request, student_id)
        qs = FeeCharge.objects.filter(school=student.school, student=student).select_related("student", "enrollment__class_level", "enrollment__class_arm", "fee_schedule__academic_session", "fee_schedule__term").annotate(ledger_balance=Coalesce(Sum("ledger_entries__amount_minor"), Value(0)))
        if request.query_params.get("session"):
            qs = qs.filter(fee_schedule__academic_session_id=request.query_params["session"])
        if request.query_params.get("term"):
            qs = qs.filter(fee_schedule__term_id=request.query_params["term"])
        history = SchoolFeePayment.objects.filter(school=student.school, allocations__student=student, status__in=[SchoolFeePayment.Status.SUCCESS, SchoolFeePayment.Status.PARTIALLY_REVERSED, SchoolFeePayment.Status.REVERSED]).annotate(student_amount=Sum("allocations__amount_minor", filter=Q(allocations__student=student))).distinct().order_by("-created_at")[:100]
        payments = [{
            "reference": row.reference, "status": row.status, "channel": row.channel,
            "method": row.method, "created_at": row.created_at,
            "amount_minor": row.student_amount or 0,
        } for row in history]
        return Response({"student_id": student.pk, "school_id": student.school_id, "student_name": " ".join(filter(None, [student.first_name, student.middle_name, student.last_name])), "school": student.school.name, "summary": student_fee_summary(student), "charges": [public_charge(charge, charge.ledger_balance) for charge in qs.order_by("-fee_schedule__academic_session__start_date", "fee_schedule__term__sequence")[:200]], "payments": payments})


class ParentPaymentInitializeView(ParentFeeView):
    def post(self, request, **kwargs):
        allocations = request.data.get("allocations", [])
        if not isinstance(allocations, list) or not allocations:
            raise serializers.ValidationError({"allocations": "Select at least one outstanding fee before continuing."})
        charge_ids = [item.get("fee_charge_id") for item in allocations if isinstance(item, dict)]
        if len(charge_ids) != len(allocations) or any(not item for item in charge_ids):
            raise serializers.ValidationError({"allocations": "Select valid student fee items."})
        charges = list(FeeCharge.objects.filter(pk__in=charge_ids).select_related("student", "school", "fee_schedule"))
        if len(charges) != len(set(charge_ids)) or len({charge.school_id for charge in charges}) != 1:
            raise serializers.ValidationError({"allocations": "Online payments can include fees from one school at a time."})
        school = charges[0].school
        linked_ids = set(linked_student_queryset(request.user).values_list("id", flat=True))
        if any(charge.student_id not in linked_ids for charge in charges):
            raise Http404
        total = 0
        normalized = []
        charges_by_id = {charge.pk: charge for charge in charges}
        for item in allocations:
            charge = charges_by_id[item["fee_charge_id"]]
            try:
                amount = int(item.get("amount_minor"))
            except (TypeError, ValueError):
                raise serializers.ValidationError({"allocations": "Enter a valid amount for each selected fee."}) from None
            if amount <= 0 or amount > charge_balance(charge):
                raise serializers.ValidationError({"allocations": "A payment amount must be greater than zero and no higher than the outstanding fee."})
            normalized.append({"fee_charge_id": charge.pk, "amount_minor": amount})
            total += amount
        setting = getattr(school, "fee_payment_settings", None)
        if not setting or not setting.online_enabled or not setting.provider_account_id:
            raise serializers.ValidationError({"detail": "This school has not enabled online fee payments yet. Contact the school office to pay in person."})
        guardian = self.guardian_for_student(request, charges[0].student)
        if guardian is None:
            raise serializers.ValidationError({"detail": "A guardian profile linked to this student is required to make an online payment."})
        reference = f"EDUF-{timezone.now():%y%m%d}-{__import__('secrets').token_hex(6).upper()}"
        payment = SchoolFeePayment.objects.create(
            school=school, channel=SchoolFeePayment.Channel.ONLINE,
            method=SchoolFeePayment.Method.CARD, provider=setting.provider,
            reference=reference, amount_minor=total, currency="NGN", status=SchoolFeePayment.Status.PENDING,
            payer=request.user, guardian=guardian, payer_email=request.user.email,
            provider_metadata={"pending_allocations": normalized, "subaccount_id": setting.provider_account_id},
        )
        callback_url = f"{settings.FRONTEND_BASE_URL}/parent?fees_payment={reference}"
        try:
            checkout = provider_for(setting.provider).initialize(
                email=request.user.email, amount_minor=total, reference=reference,
                callback_url=callback_url, subaccount_id=setting.provider_account_id,
                channels=setting.allowed_channels,
            )
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            payment.status = SchoolFeePayment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        payment.authorization_url = checkout.get("authorization_url", "")
        payment.provider_metadata["checkout_id"] = checkout.get("id", "")
        payment.save(update_fields=["authorization_url", "provider_metadata", "updated_at"])
        return Response({"reference": payment.reference, "authorization_url": payment.authorization_url, "amount_minor": payment.amount_minor, "status": payment.status}, status=status.HTTP_201_CREATED)


class ParentPaymentDetailView(ParentFeeView):
    def get_payment(self, request, reference):
        linked_ids = linked_student_queryset(request.user).values_list("id", flat=True)
        payment = SchoolFeePayment.objects.filter(
            reference=reference,
            channel=SchoolFeePayment.Channel.ONLINE,
        ).filter(
            Q(allocations__student_id__in=linked_ids) |
            Q(payer=request.user, provider_metadata__pending_allocations__isnull=False)
        ).distinct().first()
        if payment is None:
            raise Http404
        pending_ids = {
            int(item["fee_charge_id"])
            for item in payment.provider_metadata.get("pending_allocations", [])
            if isinstance(item, dict) and str(item.get("fee_charge_id", "")).isdigit()
        }
        linked_charge_ids = set(FeeCharge.objects.filter(
            pk__in=pending_ids, student_id__in=linked_ids, school_id=payment.school_id,
        ).values_list("pk", flat=True))
        # Pending checkouts have no ledger allocations until the provider confirms payment.
        # Bind the callback to the authenticated payer and every charge's linked-student ownership.
        if payment.payer_id != request.user.pk or not pending_ids or linked_charge_ids != pending_ids:
            if not payment.allocations.filter(student_id__in=linked_ids).exists():
                raise Http404
        return payment

    def get(self, request, reference, **kwargs):
        payment = self.get_payment(request, reference)
        student_ids = set(linked_student_queryset(request.user).values_list("id", flat=True))
        return Response(public_payment(payment, student_ids=student_ids))

    def post(self, request, reference, **kwargs):
        payment = self.get_payment(request, reference)
        if payment.status != SchoolFeePayment.Status.PENDING:
            student_ids = set(linked_student_queryset(request.user).values_list("id", flat=True))
            return Response(public_payment(payment, student_ids=student_ids))
        try:
            provider = provider_for(payment.provider)
            if payment.provider == "paystack":
                result = provider.verify(payment.reference)
                result = {**result, "reference": result.get("reference"), "status": result.get("status"), "amount": result.get("amount"), "currency": result.get("currency")}
            else:
                transaction_id = request.data.get("transaction_id") or request.query_params.get("transaction_id") or payment.provider_metadata.get("checkout_id")
                result = provider.verify(transaction_id)
            transaction_data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else result
            transaction_data = dict(transaction_data)
            if payment.provider == "paystack":
                transaction_data["reference"] = transaction_data.get("reference")
                transaction_data["amount"] = transaction_data.get("amount")
            verified_reference = str(transaction_data.get("reference") or transaction_data.get("tx_ref") or "")
            if verified_reference != payment.reference:
                raise serializers.ValidationError({"payment": "The verified transaction does not match this school-fee checkout. Its status has not been changed."})
            if str(transaction_data.get("status", "")).lower() in {"failed", "cancelled", "canceled"}:
                payment.status = SchoolFeePayment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])
                return Response(public_payment(payment))
            payment, _ = confirm_online_payment(payment, transaction_data, actor=request.user)
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])) from exc
        student_ids = set(linked_student_queryset(request.user).values_list("id", flat=True))
        return Response(public_payment(payment, student_ids=student_ids))


class ParentPaymentReceiptView(ParentFeeView):
    def get(self, request, reference, **kwargs):
        linked_ids = linked_student_queryset(request.user).values_list("id", flat=True)
        payment = SchoolFeePayment.objects.filter(reference=reference, allocations__student_id__in=linked_ids, status__in=[SchoolFeePayment.Status.SUCCESS, SchoolFeePayment.Status.PARTIALLY_REVERSED, SchoolFeePayment.Status.REVERSED]).distinct().first()
        if payment is None:
            raise Http404
        response = HttpResponse(receipt_pdf(payment, student_ids=set(linked_ids)), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="fee-receipt-{payment.reference}.pdf"'
        return response


class ParentReceiptOtpView(ParentFeeView):
    def post(self, request, reference, **kwargs):
        linked_ids = linked_student_queryset(request.user).values_list("id", flat=True)
        payment = SchoolFeePayment.objects.filter(reference=reference, allocations__student_id__in=linked_ids, status=SchoolFeePayment.Status.SUCCESS).distinct().first()
        if payment is None:
            raise Http404
        guardian = Guardian.objects.filter(user=request.user, school=payment.school, student_links__student_id__in=linked_ids, student_links__is_active=True, student_links__can_receive_communications=True).distinct().first()
        if guardian is None:
            raise Http404
        if request.data.get("action") == "resend":
            try:
                resend_receipt_otp(payment=payment, guardian=guardian)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
            return Response({"detail": "A fresh receipt verification code was sent to the guardian phone on file."})
        try:
            challenge = verify_receipt_otp(payment=payment, guardian=guardian, code=request.data.get("code", ""))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", None) or exc.messages) from exc
        return Response({"verified": True, "verified_at": challenge.verified_at, "detail": "Receipt verification is complete."})


class PaymentWebhookView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, provider_name, **kwargs):
        raw = request.body
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Invalid webhook payload."}, status=400)
        if provider_name == "paystack":
            secret = settings.PAYSTACK_WEBHOOK_SECRET
            signature = request.headers.get("x-paystack-signature", "")
            expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest() if secret else ""
            data = payload.get("data") or {}
            event_type = payload.get("event", "")
            provider_event_id = f"{event_type}:{data.get('id') or data.get('reference') or ''}"
            reference = data.get("reference")
            transaction_id = data.get("reference")
            valid = bool(secret and signature and hmac.compare_digest(signature, expected))
        elif provider_name == "flutterwave":
            secret = settings.FLUTTERWAVE_WEBHOOK_SECRET
            signature = request.headers.get("verif-hash", "")
            data = payload.get("data") or {}
            event_type = payload.get("event", "")
            provider_event_id = f"{event_type}:{data.get('id') or data.get('tx_ref') or ''}"
            reference = data.get("tx_ref") or (data.get("meta") or {}).get("edustacked_reference")
            transaction_id = data.get("id")
            valid = bool(secret and signature and hmac.compare_digest(signature, secret))
        else:
            return Response({"detail": "Unknown payment provider."}, status=404)
        if not valid:
            return Response({"detail": "Webhook signature could not be verified."}, status=401)
        if not reference or not provider_event_id.strip(":"):
            return Response({"detail": "Webhook did not include the payment reference."}, status=400)
        payment = SchoolFeePayment.objects.filter(provider=provider_name, reference=reference, channel=SchoolFeePayment.Channel.ONLINE).first()
        if payment is None:
            # Unknown provider references cannot update any school balance.
            return Response({"detail": "Payment reference was not found."}, status=404)
        try:
            result = provider_for(provider_name).verify(transaction_id)
            if provider_name == "paystack":
                result["reference"] = result.get("reference")
                result["amount"] = result.get("amount")
                result["status"] = "success" if result.get("status") == "success" else result.get("status")
            payment_result = result.get("data") if isinstance(result.get("data"), dict) else result
            if str(payment_result.get("reference") or payment_result.get("tx_ref") or "") != payment.reference:
                return Response({"detail": "Provider transaction reference does not match."}, status=400)
            with transaction.atomic():
                event, created = PaymentProviderEvent.objects.get_or_create(
                    provider=provider_name, event_id=provider_event_id[:160],
                    defaults={"payment": payment, "event_type": str(event_type)[:100], "payload_hash": hashlib.sha256(raw).hexdigest()},
                )
                if not created:
                    return Response({"detail": "Duplicate event already processed."}, status=200)
                locked = SchoolFeePayment.objects.select_for_update().get(pk=payment.pk)
                if str(payment_result.get("status", "")).lower() in {"success", "successful"}:
                    confirm_online_payment(locked, payment_result)
                elif str(payment_result.get("status", "")).lower() in {"failed", "cancelled", "canceled"} and locked.status == SchoolFeePayment.Status.PENDING:
                    locked.status = SchoolFeePayment.Status.FAILED
                    locked.save(update_fields=["status", "updated_at"])
                event.processed_at = timezone.now()
                event.save(update_fields=["processed_at"])
        except (DjangoValidationError, ImproperlyConfigured) as exc:
            return Response({"detail": "The provider confirmation could not yet be reconciled; it can retry safely."}, status=503)
        return Response({"detail": "Webhook received."}, status=200)
