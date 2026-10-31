import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.report_cards.models import ReportCard, ReportCardAuditEvent, ReportCardRevision
from apps.report_cards.services import validate_revision_ready
from apps.schools.models import School

from .models import (
    CreditAccount, CreditPayment, CreditTransaction, ReconciliationIssue,
    ReportCardBilling,
)
from .providers import PaystackProvider


def paystack_signature_is_valid(raw_body, signature):
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@transaction.atomic
def _locked_account(school):
    # Locking the parent school serializes account creation and balance changes even
    # when two first-ever requests race before a CreditAccount row exists.
    School.objects.select_for_update().get(pk=school.pk)
    account, _ = CreditAccount.objects.get_or_create(school=school)
    return CreditAccount.objects.select_for_update().get(pk=account.pk)


def current_balance(school):
    account, _ = CreditAccount.objects.get_or_create(school=school)
    return account.balance


@transaction.atomic
def initialize_purchase(school, user, package, provider=None):
    provider = provider or PaystackProvider()
    email = (user.email or "").strip()
    if not email:
        raise ValidationError({"email": "A valid account email is required to purchase credits."})
    reference = f"EDU{secrets.token_hex(14)}"
    payment = CreditPayment.objects.create(
        school=school, package=package, package_name=package.name,
        credits=package.credits, amount_minor=package.price_minor,
        reference=reference, customer_email=email, created_by=user,
    )
    callback_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/app/billing?reference={reference}"
    if not settings.DEBUG and not callback_url.startswith("https://"):
        raise ValidationError({"callback_url": "Billing checkout requires an HTTPS frontend callback in production."})
    checkout = provider.initialize(email=email, amount_minor=package.price_minor, reference=reference, callback_url=callback_url)
    if not checkout.get("authorization_url", "").startswith("https://"):
        raise ValidationError({"payment": "The provider returned an invalid checkout URL."})
    payment.authorization_url = checkout["authorization_url"]
    payment.provider_metadata = {"access_code": checkout.get("access_code", "")}
    payment.save(update_fields=("authorization_url", "provider_metadata", "updated_at"))
    return payment


def _validated_success(payment, data):
    expected_amount = payment.amount_minor
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        amount = -1
    if (
        data.get("status") != "success"
        or data.get("reference") != payment.reference
        or amount != expected_amount
        or data.get("currency") != payment.currency
    ):
        raise ValidationError({"payment": "Verified provider transaction does not match this purchase."})
    customer = data.get("customer") or {}
    email = customer.get("email")
    if email and email.strip().lower() != payment.customer_email.strip().lower():
        raise ValidationError({"payment": "Verified provider customer does not match this purchase."})


@transaction.atomic
def apply_provider_result(payment, data):
    payment = CreditPayment.objects.select_for_update().select_related("school").get(pk=payment.pk)
    reference = data.get("reference")
    if reference != payment.reference:
        raise ValidationError({"payment": "Provider reference does not match this purchase."})
    status = data.get("status")
    if status == "success":
        _validated_success(payment, data)
        if payment.status == CreditPayment.Status.REVERSED:
            return payment
        account = _locked_account(payment.school)
        if payment.status != CreditPayment.Status.SUCCESS:
            account.balance += payment.credits
            account.save(update_fields=("balance", "updated_at"))
            CreditTransaction.objects.create(
                school=payment.school, kind=CreditTransaction.Kind.PURCHASE,
                amount=payment.credits, description=f"Verified purchase: {payment.package_name}",
                payment=payment, actor=None, reference_key=f"payment:{payment.reference}",
                metadata={"provider": payment.provider, "provider_transaction_id": str(data.get("id", ""))},
            )
        payment.status = CreditPayment.Status.SUCCESS
        payment.verified_at = timezone.now()
        payment.provider_transaction_id = str(data.get("id", ""))
        payment.save(update_fields=("status", "verified_at", "provider_transaction_id", "updated_at"))
    elif status in {"failed", "abandoned", "reversed"}:
        if status == "reversed" and payment.status == CreditPayment.Status.SUCCESS:
            payment.status = CreditPayment.Status.REVERSED
            payment.save(update_fields=("status", "updated_at"))
            ReconciliationIssue.objects.get_or_create(
                kind="payment_reversal", provider_reference=payment.reference,
                defaults={"school": payment.school, "payment": payment,
                          "description": "Provider reports a reversal. Credits were not automatically removed; reconcile against the remaining balance and approved refund policy."},
            )
        elif payment.status == CreditPayment.Status.PENDING:
            payment.status = CreditPayment.Status.FAILED
            payment.save(update_fields=("status", "updated_at"))
    return payment


@transaction.atomic
def finalize_report_card_with_credit(card, actor, reason=""):
    card = ReportCard.objects.select_for_update().select_related(
        "school", "student", "academic_session", "term"
    ).get(pk=card.pk)
    revision = card.revisions.select_for_update().get(revision_number=card.current_revision)
    if card.status != ReportCard.Status.APPROVED or revision.status != ReportCardRevision.Status.APPROVED:
        raise ValidationError({"status": "Only an approved report card can be finalized."})
    validate_revision_ready(revision, card)
    School.objects.select_for_update().get(pk=card.school_id)
    existing = ReportCardBilling.objects.filter(
        school_id=card.school_id, student_id=card.student_id,
        academic_session_id=card.academic_session_id, term_id=card.term_id,
    ).first()
    account = None
    if existing is None:
        account = _locked_account(card.school)
        if account.balance < 1:
            raise ValidationError({"credits": "No report-card credits are available. Purchase credits to publish this student's first report card for the term."})
    now = timezone.now()
    revision.status = ReportCardRevision.Status.FINALIZED
    revision.finalized_by = actor
    revision.finalized_at = now
    revision.save(update_fields=("status", "finalized_by", "finalized_at"))
    card.status = ReportCard.Status.FINALIZED
    card.finalized_by = actor
    card.finalized_at = now
    card.save(update_fields=("status", "finalized_by", "finalized_at", "updated_at"))
    if existing is None:
        billing = ReportCardBilling.objects.create(
            school=card.school, student=card.student,
            academic_session=card.academic_session, term=card.term,
            report_card=card, revision=revision, charged_at=now,
        )
        account.balance -= 1
        account.save(update_fields=("balance", "updated_at"))
        CreditTransaction.objects.create(
            school=card.school, kind=CreditTransaction.Kind.REPORT_CARD,
            amount=-1, description=f"First publication for {card.student} — {card.term}",
            report_card_billing=billing, actor=actor,
            reference_key=f"report-card:{card.school_id}:{card.student_id}:{card.academic_session_id}:{card.term_id}",
        )
        charged = True
        balance = account.balance
    else:
        existing.report_card = card
        existing.revision = revision
        existing.save(update_fields=("report_card", "revision"))
        charged = False
        balance = current_balance(card.school)
    ReportCardAuditEvent.objects.create(
        report_card=card, revision=revision, actor=actor, action="finalized",
        reason=reason, metadata={"credit_charged": charged, "credit_balance": balance},
    )
    from apps.parent_portal.services import notify_guardians_for_student

    notify_guardians_for_student(
        card.student, f"report-card:{card.pk}:revision:{revision.pk}:published",
        "report_card_published", "Report card published",
        "A finalized report card is available in the parent portal.",
    )
    return card, revision, {"credit_charged": charged, "credit_balance": balance}


@transaction.atomic
def platform_adjustment(school, actor, amount, reason, reference_key):
    if not reason.strip():
        raise ValidationError({"reason": "An adjustment reason is required."})
    if not reference_key.strip():
        raise ValidationError({"reference_key": "An idempotency reference is required."})
    if CreditTransaction.objects.filter(reference_key=reference_key).exists():
        raise ValidationError({"reference_key": "This adjustment reference has already been used."})
    account = _locked_account(school)
    if amount == 0 or account.balance + amount < 0:
        raise ValidationError({"amount": "Adjustment must be nonzero and cannot make the credit balance negative."})
    account.balance += amount
    account.save(update_fields=("balance", "updated_at"))
    return CreditTransaction.objects.create(
        school=school, kind=CreditTransaction.Kind.ADJUSTMENT, amount=amount,
        description=reason.strip(), actor=actor, reference_key=reference_key.strip(),
    )
