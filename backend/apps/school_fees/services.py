"""Shared fee issue, balance, payment, SMS, receipt and verification services."""
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.academics.models import AcademicSession, Term
from apps.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

from .models import (
    FeeCharge, FeeLedgerEntry, FeeNotification, FeePaymentAllocation, FeeSchedule,
    PaymentReversal, ReceiptOtpChallenge, SchoolFeePayment,
)


def ledger_balance(*, student, fee_charge=None):
    rows = FeeLedgerEntry.objects.filter(school_id=student.school_id, student=student)
    if fee_charge is not None:
        rows = rows.filter(fee_charge=fee_charge)
    else:
        rows = rows.filter(fee_charge__isnull=True)
    return int(rows.aggregate(total=Sum("amount_minor"))["total"] or 0)


def charge_balance(charge, *, lock=False):
    if lock:
        FeeCharge.objects.select_for_update().filter(pk=charge.pk).exists()
    return max(0, ledger_balance(student=charge.student, fee_charge=charge))


@transaction.atomic
def issue_fee_schedule(schedule, actor):
    schedule = FeeSchedule.objects.select_for_update().select_related("school", "academic_session", "term", "class_level").get(pk=schedule.pk)
    if schedule.status != FeeSchedule.Status.ACTIVE:
        raise ValidationError("Only active fee schedules can be issued to students.")
    enrollments = StudentEnrollment.objects.filter(
        school=schedule.school, academic_session=schedule.academic_session,
        class_level=schedule.class_level, status=StudentEnrollment.Status.ACTIVE,
    ).select_related("student")
    if schedule.class_arm_id:
        enrollments = enrollments.filter(class_arm_id=schedule.class_arm_id)
    issued = 0
    for enrollment in enrollments.iterator():
        charge, created = FeeCharge.objects.get_or_create(
            fee_schedule=schedule, student=enrollment.student,
            defaults={"school": schedule.school, "enrollment": enrollment, "amount_minor": schedule.amount_minor, "created_by": actor},
        )
        if not created:
            continue
        FeeLedgerEntry.objects.create(
            school=schedule.school, student=enrollment.student, fee_charge=charge,
            kind=FeeLedgerEntry.Kind.CHARGE, amount_minor=charge.amount_minor,
            description=f"{schedule.category} · {schedule.term.name}",
            reference_key=f"fee-charge:{charge.pk}", actor=actor,
        )
        issued += 1
        apply_student_credit(enrollment.student, actor=actor)
    return issued


def apply_student_credit(student, *, actor=None):
    """Apply any unapplied student credit to the oldest outstanding fees."""
    credit = max(0, -ledger_balance(student=student))
    if not credit:
        return 0
    charges = FeeCharge.objects.filter(school_id=student.school_id, student=student).select_related("fee_schedule").order_by("fee_schedule__due_date", "created_at", "id")
    applied = 0
    for charge in charges:
        outstanding = charge_balance(charge)
        amount = min(credit - applied, outstanding)
        if amount <= 0:
            continue
        marker = secrets.token_hex(6)
        FeeLedgerEntry.objects.create(
            school_id=student.school_id, student=student, fee_charge=charge,
            kind=FeeLedgerEntry.Kind.CREDIT_APPLICATION, amount_minor=-amount,
            description=f"Previously received credit applied to {charge.fee_schedule.category}",
            reference_key=f"fee-credit-apply:{student.pk}:{charge.pk}:{marker}:charge", actor=actor,
        )
        FeeLedgerEntry.objects.create(
            school_id=student.school_id, student=student,
            kind=FeeLedgerEntry.Kind.CREDIT_APPLICATION, amount_minor=amount,
            description=f"Unapplied credit moved to {charge.fee_schedule.category}",
            reference_key=f"fee-credit-apply:{student.pk}:{charge.pk}:{marker}:credit", actor=actor,
        )
        applied += amount
        if applied >= credit:
            break
    return applied


def student_fee_summary(student, *, academic_session=None, term=None):
    charges = FeeCharge.objects.filter(school_id=student.school_id, student=student)
    if academic_session:
        charges = charges.filter(fee_schedule__academic_session=academic_session)
    if term:
        charges = charges.filter(fee_schedule__term=term)
    expected = int(charges.aggregate(total=Sum("amount_minor"))["total"] or 0)
    charge_ids = list(charges.values_list("id", flat=True))
    net_balance = int(FeeLedgerEntry.objects.filter(
        school_id=student.school_id, student=student, fee_charge_id__in=charge_ids,
    ).aggregate(total=Sum("amount_minor"))["total"] or 0)
    paid = max(0, expected - net_balance)
    credit = max(0, -ledger_balance(student=student))
    return {"expected_minor": expected, "paid_minor": paid, "outstanding_minor": max(0, expected - paid), "credit_minor": credit}


def _write_allocations(payment, allocations, actor=None, *, allow_excess=False):
    """Allocate a settled payment; excess goes to a student's unallocated credit."""
    total = 0
    touched_students = set()
    for item in allocations:
        charge_id = item.get("fee_charge_id") or item.get("charge_id")
        amount = int(item.get("amount_minor", 0))
        if amount <= 0:
            raise ValidationError({"allocations": "Each allocation must be greater than zero."})
        charge = None
        if charge_id:
            charge = FeeCharge.objects.select_for_update().select_related("student", "school", "fee_schedule").filter(
                pk=charge_id, school=payment.school,
            ).first()
            if charge is None:
                raise ValidationError({"allocations": "A selected fee does not belong to this school."})
            outstanding = charge_balance(charge)
            if amount > outstanding:
                if not allow_excess:
                    raise ValidationError({"allocations": f"The amount for {charge.fee_schedule.category} is higher than the outstanding balance."})
                excess = amount - outstanding
                charge_amount = outstanding
            else:
                excess = 0
                charge_amount = amount
            if charge_amount:
                allocation = FeePaymentAllocation.objects.create(
                    payment=payment, school=payment.school, student=charge.student, fee_charge=charge,
                    amount_minor=charge_amount, balance_before_minor=outstanding,
                    balance_after_minor=outstanding - charge_amount,
                )
                FeeLedgerEntry.objects.create(
                    school=payment.school, student=charge.student, fee_charge=charge, payment=payment,
                    allocation=allocation, kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor=-charge_amount,
                    description=f"Payment {payment.reference}", reference_key=f"fee-payment:{payment.reference}:allocation:{allocation.pk}", actor=actor,
                )
                total += charge_amount
            touched_students.add(charge.student_id)
            if excess:
                FeePaymentAllocation.objects.create(payment=payment, school=payment.school, student=charge.student, amount_minor=excess)
                allocation = payment.allocations.order_by("-id").first()
                FeeLedgerEntry.objects.create(
                    school=payment.school, student=charge.student, payment=payment, allocation=allocation,
                    kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor=-excess,
                    description=f"Unapplied payment credit · {payment.reference}", reference_key=f"fee-payment:{payment.reference}:credit:{allocation.pk}", actor=actor,
                )
                total += excess
        else:
            student_id = item.get("student_id")
            student = Student.objects.filter(pk=student_id, school=payment.school).first()
            if student is None:
                raise ValidationError({"allocations": "Choose a student from this school for an unapplied credit."})
            FeePaymentAllocation.objects.create(payment=payment, school=payment.school, student=student, amount_minor=amount)
            allocation = payment.allocations.order_by("-id").first()
            FeeLedgerEntry.objects.create(
                school=payment.school, student=student, payment=payment, allocation=allocation,
                kind=FeeLedgerEntry.Kind.PAYMENT, amount_minor=-amount,
                description=f"Unapplied payment credit · {payment.reference}", reference_key=f"fee-payment:{payment.reference}:credit:{allocation.pk}", actor=actor,
            )
            touched_students.add(student.pk)
            total += amount
    if total != payment.amount_minor:
        raise ValidationError({"amount_minor": "Payment allocations must add up to the amount received."})
    students = Student.objects.filter(pk__in=touched_students, school=payment.school)
    for student in students:
        apply_student_credit(student, actor=actor)
    return touched_students


@transaction.atomic
def record_physical_payment(*, school, actor, amount_minor, method, allocations, description="", payer_email=""):
    try:
        amount_minor = int(amount_minor)
    except (TypeError, ValueError):
        raise ValidationError({"amount_minor": "Enter a valid amount in naira."}) from None
    if amount_minor <= 0:
        raise ValidationError({"amount_minor": "Payment amount must be greater than zero."})
    if method not in SchoolFeePayment.Method.values:
        raise ValidationError({"method": "Choose cash, POS, bank transfer, or another supported method."})
    if not allocations:
        raise ValidationError({"allocations": "Choose at least one student fee to receive this payment."})
    if not isinstance(allocations, list) or any(not isinstance(item, dict) for item in allocations):
        raise ValidationError({"allocations": "Payment allocations must be a list of selected student fees."})
    first = allocations[0]
    first_charge = FeeCharge.objects.filter(pk=first.get("fee_charge_id") or first.get("charge_id"), school=school).first() if first.get("fee_charge_id") or first.get("charge_id") else None
    first_student_id = first_charge.student_id if first_charge else first.get("student_id")
    guardian = Guardian.objects.filter(
        school=school, is_active=True, student_links__school=school,
        student_links__student_id=first_student_id, student_links__is_active=True,
        student_links__can_receive_communications=True,
    ).order_by("-student_links__is_primary_contact", "id").first()
    reference = f"EDUF-{timezone.now():%y%m%d}-{secrets.token_hex(6).upper()}"
    payment = SchoolFeePayment.objects.create(
        school=school, channel=SchoolFeePayment.Channel.PHYSICAL, method=method,
        reference=reference, amount_minor=amount_minor, currency="NGN",
        status=SchoolFeePayment.Status.SUCCESS, payer_email=payer_email, guardian=guardian,
        description=description[:300], recorded_by=actor, received_at=timezone.now(),
    )
    settings_row = getattr(school, "fee_payment_settings", None)
    _write_allocations(payment, allocations, actor, allow_excess=bool(settings_row is None or settings_row.allow_excess_credit))
    transaction.on_commit(lambda: notify_payment_guardians(payment.pk))
    transaction.on_commit(lambda: issue_receipt_otp_to_guardians(payment.pk))
    return payment


@transaction.atomic
def confirm_online_payment(payment, provider_result, *, actor=None):
    payment = SchoolFeePayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == SchoolFeePayment.Status.SUCCESS:
        return payment, False
    if payment.status != SchoolFeePayment.Status.PENDING:
        return payment, False
    reference = str(provider_result.get("reference") or provider_result.get("tx_ref") or "")
    status_value = str(provider_result.get("status", "")).lower()
    amount = provider_result.get("amount")
    currency = str(provider_result.get("currency") or "").upper()
    if reference != payment.reference or status_value not in {"success", "successful"}:
        raise ValidationError({"payment": "The provider has not confirmed this payment as successful."})
    if amount is None or int(amount) != payment.amount_minor:
        raise ValidationError({"payment": "The confirmed amount does not match this school's fee payment."})
    if currency and currency != payment.currency:
        raise ValidationError({"payment": "The provider confirmed a different currency for this payment."})
    provider_method = str(provider_result.get("channel") or provider_result.get("payment_type") or "").strip().lower().replace(" ", "_")
    payment.method = {
        "card": SchoolFeePayment.Method.CARD,
        "bank": SchoolFeePayment.Method.BANK_TRANSFER,
        "banktransfer": SchoolFeePayment.Method.BANK_TRANSFER,
        "bank_transfer": SchoolFeePayment.Method.BANK_TRANSFER,
        "account": SchoolFeePayment.Method.BANK_TRANSFER,
        "ussd": SchoolFeePayment.Method.USSD,
    }.get(provider_method, SchoolFeePayment.Method.OTHER if provider_method else payment.method)
    payment.status = SchoolFeePayment.Status.SUCCESS
    payment.provider_transaction_id = str(provider_result.get("id") or provider_result.get("flw_ref") or "")[:120]
    payment.received_at = timezone.now()
    payment.save(update_fields=["method", "status", "provider_transaction_id", "received_at", "updated_at"])
    # A checkout can finish after a different checkout has already paid the
    # same balance. Once a provider confirms money received, always record the
    # full amount; any race-created excess remains visible as student credit.
    _write_allocations(payment, payment.provider_metadata.get("pending_allocations", []), actor, allow_excess=True)
    transaction.on_commit(lambda: notify_payment_guardians(payment.pk))
    transaction.on_commit(lambda: issue_receipt_otp_to_guardians(payment.pk))
    return payment, True


@transaction.atomic
def reverse_payment(*, payment, amount_minor, reason, actor, external_reference=""):
    payment = SchoolFeePayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status not in {SchoolFeePayment.Status.SUCCESS, SchoolFeePayment.Status.PARTIALLY_REVERSED}:
        raise ValidationError({"payment": "Only a successful payment can be reversed."})
    try:
        amount_minor = int(amount_minor)
    except (TypeError, ValueError):
        raise ValidationError({"amount_minor": "Enter a valid reversal amount."}) from None
    if amount_minor <= 0:
        raise ValidationError({"amount_minor": "Reversal amount must be greater than zero."})
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Explain why this payment is being reversed."})
    external_reference = str(external_reference or "").strip()[:120]
    if external_reference and payment.reversals.filter(external_reference=external_reference).exists():
        raise ValidationError({"external_reference": "This refund or adjustment reference has already been used for this payment."})
    already = int(payment.reversals.aggregate(total=Sum("amount_minor"))["total"] or 0)
    remaining = payment.amount_minor - already
    if amount_minor > remaining:
        raise ValidationError({"amount_minor": "The reversal cannot exceed the amount that has not already been reversed."})
    reversal = PaymentReversal.objects.create(payment=payment, amount_minor=amount_minor, reason=reason[:500], external_reference=external_reference, recorded_by=actor)
    allocations = list(payment.allocations.select_related("student", "fee_charge").order_by("id"))
    left = amount_minor
    for allocation in allocations:
        previous_reversed = int(FeeLedgerEntry.objects.filter(reversal__payment=payment, allocation=allocation, kind=FeeLedgerEntry.Kind.REFUND).aggregate(total=Sum("amount_minor"))["total"] or 0)
        available = allocation.amount_minor - previous_reversed
        take = min(left, available)
        if take <= 0:
            continue
        FeeLedgerEntry.objects.create(
            school=payment.school, student=allocation.student, fee_charge=allocation.fee_charge,
            payment=payment, allocation=allocation, reversal=reversal,
            kind=FeeLedgerEntry.Kind.REFUND, amount_minor=take,
            description=reason.strip()[:300], reference_key=f"fee-reversal:{reversal.pk}:allocation:{allocation.pk}", actor=actor,
        )
        left -= take
        if left == 0:
            break
    if left:
        raise ValidationError("This payment's allocation history could not be reversed safely. Contact support.")
    payment.status = SchoolFeePayment.Status.REVERSED if amount_minor + already == payment.amount_minor else SchoolFeePayment.Status.PARTIALLY_REVERSED
    payment.save(update_fields=["status", "updated_at"])
    return reversal


def _termii_send(phone, message):
    api_key = getattr(settings, "TERMII_API_KEY", "")
    sender = getattr(settings, "TERMII_SENDER_ID", "")
    if not api_key or not sender:
        raise ImproperlyConfigured("SMS delivery is not set up yet. Ask the platform administrator to configure Termii.")
    destination = re.sub(r"\D", "", str(phone or ""))
    if destination.startswith("0") and len(destination) == 11:
        destination = f"234{destination[1:]}"
    elif len(destination) == 10 and destination.startswith(("7", "8", "9")):
        destination = f"234{destination}"
    if len(destination) < 10 or len(destination) > 15:
        raise ValidationError("The guardian phone number is not in a valid international format.")
    payload = {
        "api_key": api_key, "to": destination, "from": sender, "sms": message,
        "type": "plain", "channel": getattr(settings, "TERMII_CHANNEL", "generic"),
    }
    request = Request(f"{settings.TERMII_BASE_URL}/api/sms/send", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ValidationError("Termii could not deliver this SMS. The payment is safely recorded; retry the notification later.") from exc
    accepted = isinstance(result, dict) and (
        result.get("code") in ("ok", "200", 200)
        or (result.get("message_id") and str(result.get("message", "")).lower().startswith("successfully sent"))
    )
    if not accepted:
        raise ValidationError("Termii did not confirm SMS delivery. The payment is safely recorded; retry the notification later.")
    return str(result.get("message_id") or result.get("messageId") or "")


def send_fee_sms(*, school, payment, guardian, kind, message):
    phone = guardian.phone.strip()
    notification = FeeNotification.objects.create(school=school, payment=payment, guardian=guardian, kind=kind, phone=phone)
    notification.attempt_count += 1
    notification.last_attempt_at = timezone.now()
    try:
        message_id = _termii_send(phone, message)
        notification.status = FeeNotification.Status.SENT
        notification.provider_message_id = message_id
        notification.sent_at = timezone.now()
        notification.last_error = ""
    except (ImproperlyConfigured, ValidationError) as exc:
        notification.status = FeeNotification.Status.FAILED
        notification.last_error = str(getattr(exc, "messages", [str(exc)])[0])[:300]
    notification.save(update_fields=["attempt_count", "last_attempt_at", "status", "provider_message_id", "sent_at", "last_error"])
    return notification


def payment_amount_for_guardian(payment, guardian):
    student_ids = guardian.student_links.filter(
        school=payment.school, is_active=True, can_receive_communications=True,
    ).values_list("student_id", flat=True)
    return int(payment.allocations.filter(student_id__in=student_ids).aggregate(total=Sum("amount_minor"))["total"] or 0)


def notify_payment_guardians(payment_id):
    payment = SchoolFeePayment.objects.select_related("school").filter(pk=payment_id, status=SchoolFeePayment.Status.SUCCESS).first()
    if not payment:
        return
    guardian_ids = payment.allocations.filter(
        student__guardian_links__school=payment.school,
        student__guardian_links__is_active=True,
        student__guardian_links__can_receive_communications=True,
        student__guardian_links__guardian__is_active=True,
    ).values_list("student__guardian_links__guardian_id", flat=True).distinct()
    guardians = Guardian.objects.filter(pk__in=guardian_ids).distinct()
    for guardian in guardians:
        if guardian.phone:
            amount_minor = payment_amount_for_guardian(payment, guardian)
            if not amount_minor:
                continue
            amount = f"NGN {amount_minor / 100:,.2f}"
            send_fee_sms(school=payment.school, payment=payment, guardian=guardian, kind=FeeNotification.Kind.PAYMENT_RECEIPT,
                         message=f"{payment.school.name}: We recorded {amount} for school fees. Receipt {payment.reference}. Keep this reference for your records.")


def _otp_hash(payment, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"school-fee-receipt:{payment.reference}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_receipt_otp_to_guardians(payment_id):
    payment = SchoolFeePayment.objects.select_related("school").filter(pk=payment_id, status=SchoolFeePayment.Status.SUCCESS).first()
    if not payment:
        return
    guardian_ids = payment.allocations.filter(
        student__guardian_links__school=payment.school, student__guardian_links__is_active=True,
        student__guardian_links__can_receive_communications=True, student__guardian_links__guardian__is_active=True,
    ).values_list("student__guardian_links__guardian_id", flat=True).distinct()
    for guardian in Guardian.objects.filter(pk__in=guardian_ids).distinct():
        if not guardian.phone:
            continue
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = ReceiptOtpChallenge.objects.create(
            payment=payment, guardian=guardian, phone_snapshot=guardian.phone[:30],
            code_hash=_otp_hash(payment, code), expires_at=timezone.now() + timedelta(minutes=10),
        )
        send_fee_sms(school=payment.school, payment=payment, guardian=guardian, kind=FeeNotification.Kind.RECEIPT_OTP,
                     message=f"{payment.school.name}: Receipt verification code {code} for {payment.reference}. Expires in 10 minutes. Do not share it.")
        # Keep the challenge even if delivery fails so an authorised resend can issue a fresh code.
        if challenge.pk:
            continue


def verify_receipt_otp(*, payment, guardian, code):
    error = None
    challenge = None
    with transaction.atomic():
        challenge = ReceiptOtpChallenge.objects.select_for_update().filter(payment=payment, guardian=guardian, verified_at__isnull=True).order_by("-created_at").first()
        if challenge is None:
            error = "No active receipt code was found. Request a new code."
        elif challenge.expires_at <= timezone.now():
            error = "This receipt code has expired. Request a new one."
        elif challenge.attempts >= 5:
            error = "Too many incorrect attempts. Request a new receipt code."
        else:
            challenge.attempts += 1
            if not hmac.compare_digest(challenge.code_hash, _otp_hash(payment, str(code).strip())):
                challenge.save(update_fields=["attempts"])
                error = "That code did not match. Check the SMS and try again."
            else:
                challenge.verified_at = timezone.now()
                challenge.save(update_fields=["attempts", "verified_at"])
    if error:
        raise ValidationError({"code": error})
    return challenge


def resend_receipt_otp(*, payment, guardian):
    now = timezone.now()
    sent_recently = ReceiptOtpChallenge.objects.filter(payment=payment, guardian=guardian, created_at__gte=now - timedelta(hours=1)).count()
    if sent_recently >= 4:
        raise ValidationError({"code": "You have reached the receipt-code resend limit. Try again later."})
    if not guardian.phone:
        raise ValidationError({"phone": "No guardian phone number is saved for this account. Contact the school."})
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = ReceiptOtpChallenge.objects.create(payment=payment, guardian=guardian, phone_snapshot=guardian.phone[:30], code_hash=_otp_hash(payment, code), expires_at=now + timedelta(minutes=10), resend_count=sent_recently)
    notification = send_fee_sms(school=payment.school, payment=payment, guardian=guardian, kind=FeeNotification.Kind.RECEIPT_OTP,
                                message=f"{payment.school.name}: Receipt verification code {code} for {payment.reference}. Expires in 10 minutes. Do not share it.")
    if notification.status != FeeNotification.Status.SENT:
        raise ValidationError({"detail": "The receipt is recorded, but the SMS could not be delivered. You can retry later."})
    return challenge
