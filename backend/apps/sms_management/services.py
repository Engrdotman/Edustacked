import hashlib
import hmac
import json
import math
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.providers import FlutterwaveProvider, PaystackProvider
from apps.schools.models import School

from .models import (
    SMSBundle, SMSMessageBatch, SMSMessageLog, SMSMonthlyAllowance,
    SMSPlatformConfiguration, SMSPurchase, SMSWallet, SMSWalletTransaction,
)


class TermiiRejected(Exception):
    """Termii explicitly rejected a message, so its debit can safely be reversed."""


class TermiiOutcomeUnknown(Exception):
    """A timeout or malformed response may have happened after Termii accepted the send."""


def platform_config():
    config, _ = SMSPlatformConfiguration.objects.get_or_create(key="platform")
    return config


def _month_start(value=None):
    value = value or timezone.localdate()
    return date(value.year, value.month, 1)


def ensure_monthly_allowance(school, *, on_date=None):
    config = platform_config()
    allowance, _ = SMSMonthlyAllowance.objects.get_or_create(
        school=school, month_start=_month_start(on_date),
        defaults={"allowance_credits": config.monthly_free_allowance},
    )
    return allowance


def issue_monthly_allowances(*, on_date=None):
    config = platform_config()
    period = _month_start(on_date)
    created = 0
    for school_id in School.objects.filter(is_active=True).values_list("pk", flat=True).iterator():
        _, was_created = SMSMonthlyAllowance.objects.get_or_create(
            school_id=school_id, month_start=period,
            defaults={"allowance_credits": config.monthly_free_allowance},
        )
        created += int(was_created)
    return {"month_start": period, "created": created, "schools": School.objects.filter(is_active=True).count()}


_GSM_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXTENDED = frozenset("^{}\\[~]|€")


def sms_segments(message):
    text = str(message or "")
    if not text:
        raise ValidationError({"message": "Enter the SMS message before sending."})
    if any(character not in _GSM_BASIC and character not in _GSM_EXTENDED for character in text):
        units = len(text)
        return 1 if units <= 70 else math.ceil(units / 67)
    units = sum(2 if character in _GSM_EXTENDED else 1 for character in text)
    return 1 if units <= 160 else math.ceil(units / 153)


def normalize_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    elif len(digits) == 10 and digits[0] in "789":
        digits = "234" + digits
    if not 10 <= len(digits) <= 15:
        raise ValidationError({"recipients": f"The phone number {value!s} is not a valid international number."})
    return digits


def termii_send_raw(phone, message):
    api_key = getattr(settings, "TERMII_API_KEY", "")
    sender = getattr(settings, "TERMII_SENDER_ID", "")
    if not api_key or not sender:
        raise ImproperlyConfigured("SMS sending is not configured yet. Ask EDUstacked to complete the Termii setup.")
    destination = normalize_phone(phone)
    payload = {
        "api_key": api_key,
        "to": destination,
        "from": sender,
        "sms": message,
        "type": "plain",
        "channel": getattr(settings, "TERMII_CHANNEL", "generic"),
    }
    request = Request(
        f"{settings.TERMII_BASE_URL}/api/sms/send",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise TermiiOutcomeUnknown("Termii did not confirm the request. The SMS status is being held for review.") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise TermiiOutcomeUnknown("Termii returned an unreadable response. The SMS status is being held for review.") from exc
    accepted = isinstance(result, dict) and (
        result.get("code") in ("ok", "200", 200)
        or (result.get("message_id") and str(result.get("message", "")).lower().startswith("successfully sent"))
    )
    if not accepted:
        raise TermiiRejected("Termii did not accept this message.")
    message_id = result.get("message_id") or result.get("messageId") or ""
    if not message_id:
        raise TermiiOutcomeUnknown("Termii accepted a message without returning its reference. The status needs review.")
    return str(message_id)


def _serialize_batch(batch, *, replayed=False):
    rows = list(batch.messages.all())
    return {
        "id": batch.pk,
        "status": batch.status,
        "recipient_count": batch.recipient_count,
        "total_segments": batch.total_segments,
        "free_credits": batch.free_credits,
        "paid_credits": batch.paid_credits,
        "replayed": replayed,
        "messages": [{
            "id": row.pk, "phone": row.phone, "segments": row.segments,
            "free_credits": row.free_credits, "paid_credits": row.paid_credits,
            "status": row.status, "provider_message_id": row.provider_message_id,
            "last_error": row.last_error, "created_at": row.created_at,
        } for row in rows],
    }


@transaction.atomic
def _refund_failed_message(message, *, reason):
    message = SMSMessageLog.objects.select_for_update().select_related("school", "batch").get(pk=message.pk)
    if message.status == SMSMessageLog.Status.FAILED and message.last_error.startswith("Refunded:"):
        return message
    School.objects.select_for_update().get(pk=message.school_id)
    wallet, _ = SMSWallet.objects.get_or_create(school_id=message.school_id)
    wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
    if message.paid_credits:
        wallet.purchased_balance += message.paid_credits
        wallet.paid_value_balance_minor += message.paid_sales_value_minor
        SMSWalletTransaction.objects.get_or_create(
            reference_key=f"sms-message-refund:{message.pk}",
            defaults={
                "school_id": message.school_id,
                "kind": SMSWalletTransaction.Kind.REFUND,
                "credits": message.paid_credits,
                "description": "Refund for a message confirmed failed by Termii",
                "message": message,
                "actor": None,
                "metadata": {"reason": reason[:300], "paid_value_restored_minor": message.paid_sales_value_minor},
            },
        )
    allowance_month = _month_start(message.created_at.astimezone(timezone.get_current_timezone()).date())
    allowance = SMSMonthlyAllowance.objects.select_for_update().filter(school_id=message.school_id, month_start=allowance_month).first()
    if allowance and message.free_credits:
        allowance.used_credits = max(0, allowance.used_credits - message.free_credits)
        allowance.save(update_fields=("used_credits", "updated_at"))
    wallet.save(update_fields=("purchased_balance", "paid_value_balance_minor", "updated_at"))
    message.status = SMSMessageLog.Status.FAILED
    message.last_error = f"Refunded: {reason}"[:300]
    message.save(update_fields=("status", "last_error"))
    batch = SMSMessageBatch.objects.select_for_update().get(pk=message.batch_id)
    _update_batch_status(batch)
    return message


def _update_batch_status(batch):
    statuses = list(batch.messages.values_list("status", flat=True))
    submitted = sum(value in (SMSMessageLog.Status.SUBMITTED, SMSMessageLog.Status.DELIVERED) for value in statuses)
    unknown = sum(value == SMSMessageLog.Status.UNKNOWN for value in statuses)
    if submitted == len(statuses):
        batch.status = SMSMessageBatch.Status.SUBMITTED
    elif submitted or unknown:
        batch.status = SMSMessageBatch.Status.PARTIAL
    else:
        batch.status = SMSMessageBatch.Status.FAILED
    batch.save(update_fields=("status",))


def send_school_sms(*, school, actor, recipients, message, idempotency_key):
    if not getattr(settings, "TERMII_API_KEY", "") or not getattr(settings, "TERMII_SENDER_ID", ""):
        raise ImproperlyConfigured("SMS sending is not configured yet. Ask EDUstacked to complete the Termii setup.")
    body = str(message or "").strip()
    if not body or len(body) > 5000:
        raise ValidationError({"message": "Enter a message between 1 and 5,000 characters."})
    if not isinstance(recipients, (list, tuple)) or not recipients or len(recipients) > 200:
        raise ValidationError({"recipients": "Enter between 1 and 200 recipient phone numbers."})
    phones = list(dict.fromkeys(normalize_phone(phone) for phone in recipients))
    if len(phones) > 200:
        raise ValidationError({"recipients": "Enter no more than 200 unique phone numbers per send."})
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValidationError({"detail": "A valid message request key is required. Refresh and submit again."})
    segments = sms_segments(body)
    payload_hash = hashlib.sha256(json.dumps({"phones": phones, "message": body}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    with transaction.atomic():
        School.objects.select_for_update().get(pk=school.pk)
        existing = SMSMessageBatch.objects.filter(school=school, idempotency_key=idempotency_key).first()
        if existing:
            if existing.payload_hash != payload_hash:
                raise ValidationError({"detail": "This request key was already used for a different SMS. Refresh and try again."})
            return _serialize_batch(existing, replayed=True)

        wallet, _ = SMSWallet.objects.get_or_create(school=school)
        wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
        if wallet.sending_suspended:
            raise ValidationError({"detail": "SMS sending is paused for this school. Contact EDUstacked support."})
        allowance = ensure_monthly_allowance(school)
        allowance = SMSMonthlyAllowance.objects.select_for_update().get(pk=allowance.pk)
        total_credits = len(phones) * segments
        free_available = max(0, allowance.allowance_credits - allowance.used_credits)
        free_credits = min(free_available, total_credits)
        paid_credits = total_credits - free_credits
        if paid_credits > wallet.purchased_balance:
            needed = paid_credits - wallet.purchased_balance
            raise ValidationError({"detail": f"Not enough SMS credits. Your monthly free allowance is used up and you need {needed} more purchased credit(s). Buy an SMS bundle to continue."})

        paid_balance_before = wallet.purchased_balance
        value_to_consume = 0
        if paid_credits:
            value_to_consume = wallet.paid_value_balance_minor if paid_credits == paid_balance_before else int(
                (Decimal(wallet.paid_value_balance_minor) * Decimal(paid_credits) / Decimal(paid_balance_before)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        config = platform_config()
        batch = SMSMessageBatch.objects.create(
            school=school, idempotency_key=idempotency_key, payload_hash=payload_hash,
            recipient_count=len(phones), total_segments=total_credits,
            free_credits=free_credits, paid_credits=paid_credits, created_by=actor,
        )
        remaining_free = free_credits
        remaining_paid_value = value_to_consume
        for index, phone in enumerate(phones):
            row_free = min(segments, remaining_free)
            row_paid = segments - row_free
            remaining_free -= row_free
            row_value = 0
            if row_paid:
                row_value = remaining_paid_value if index == len(phones) - 1 or row_paid == paid_credits else int(
                    (Decimal(value_to_consume) * Decimal(row_paid) / Decimal(paid_credits)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )
                row_value = min(row_value, remaining_paid_value)
                remaining_paid_value -= row_value
            log = SMSMessageLog.objects.create(
                school=school, batch=batch, phone=phone, message=body, segments=segments,
                free_credits=row_free, paid_credits=row_paid,
                paid_sales_value_minor=row_value,
                provider_cost_estimate_minor=segments * config.provider_cost_per_credit_minor,
                paid_provider_cost_estimate_minor=row_paid * config.provider_cost_per_credit_minor,
                status=SMSMessageLog.Status.QUEUED,
            )
            if row_paid:
                unit_price = row_value // row_paid if row_paid else 0
                SMSWalletTransaction.objects.create(
                    school=school, kind=SMSWalletTransaction.Kind.CONSUMPTION,
                    credits=-row_paid, description="SMS sent",
                    reference_key=f"sms-message-consumption:{log.pk}",
                    message=log, actor=actor, unit_sale_price_minor=unit_price,
                    provider_cost_per_credit_minor=config.provider_cost_per_credit_minor,
                    metadata={"paid_value_consumed_minor": row_value, "free_credits": row_free, "segments": segments},
                )
        allowance.used_credits += free_credits
        allowance.save(update_fields=("used_credits", "updated_at"))
        wallet.purchased_balance -= paid_credits
        wallet.paid_value_balance_minor -= value_to_consume
        wallet.save(update_fields=("purchased_balance", "paid_value_balance_minor", "updated_at"))

    for log in batch.messages.order_by("id"):
        try:
            message_id = termii_send_raw(log.phone, body)
        except TermiiRejected as exc:
            _refund_failed_message(log, reason=str(exc))
            continue
        except TermiiOutcomeUnknown as exc:
            SMSMessageLog.objects.filter(pk=log.pk).update(status=SMSMessageLog.Status.UNKNOWN, last_error=str(exc)[:300])
            continue
        except ImproperlyConfigured:
            _refund_failed_message(log, reason="Termii is not configured.")
            continue
        except Exception as exc:
            # Unknown provider errors are treated as ambiguous; a refund could duplicate a delivered SMS.
            SMSMessageLog.objects.filter(pk=log.pk).update(status=SMSMessageLog.Status.UNKNOWN, last_error="Termii response needs reconciliation.")
            continue
        SMSMessageLog.objects.filter(pk=log.pk).update(
            status=SMSMessageLog.Status.SUBMITTED, provider_message_id=message_id,
            sent_at=timezone.now(), last_error="",
        )
    batch.refresh_from_db()
    _update_batch_status(batch)
    batch.refresh_from_db()
    return _serialize_batch(batch)


def termii_signature_is_valid(raw_body, signature):
    secret = getattr(settings, "TERMII_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@transaction.atomic
def apply_delivery_report(payload):
    provider_message_id = str(payload.get("message_id") or "")
    if not provider_message_id:
        raise ValidationError("The delivery update did not include a message reference.")
    message = SMSMessageLog.objects.select_for_update().filter(provider_message_id=provider_message_id).first()
    if message is None:
        return None
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    event_key = f"delivery:{provider_message_id}:{event_hash}"
    from .models import SMSProviderEvent
    _, created = SMSProviderEvent.objects.get_or_create(
        provider="termii", event_id=event_key[:160],
        defaults={"message": message, "event_type": str(payload.get("status", ""))[:80], "payload_hash": event_hash},
    )
    if not created:
        return message
    state = str(payload.get("status") or "").strip().lower()
    if state in {"delivered", "message delivered to handset"}:
        message.status = SMSMessageLog.Status.DELIVERED
        message.delivered_at = timezone.now()
    elif state in {"message failed", "rejected", "dnd active on phone number", "expired"}:
        message = _refund_failed_message(message, reason=f"Termii delivery report: {state}")
    elif state in {"message sent", "sent", "accepted", "submitted"}:
        message.status = SMSMessageLog.Status.SUBMITTED
    else:
        message.last_error = f"Termii reported an unrecognized delivery status: {state[:80]}"
    try:
        cost = Decimal(str(payload.get("cost")))
        if cost.is_finite() and cost >= 0:
            message.actual_provider_cost_minor = int((cost * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        pass
    message.save(update_fields=("status", "delivered_at", "actual_provider_cost_minor", "last_error"))
    SMSProviderEvent.objects.filter(provider="termii", event_id=event_key[:160]).update(processed_at=timezone.now())
    return message


def _provider_instance(provider):
    if provider == SMSPurchase.Provider.PAYSTACK:
        return PaystackProvider()
    if provider == SMSPurchase.Provider.FLUTTERWAVE:
        return FlutterwaveProvider()
    raise ValidationError({"provider": "Choose Paystack or Flutterwave for the SMS bundle checkout."})


def initialize_sms_purchase(*, school, user, bundle, provider_name):
    provider_name = str(provider_name or "").lower()
    provider = _provider_instance(provider_name)
    email = (user.email or "").strip()
    if not email:
        raise ValidationError({"email": "Add an email address to your account before purchasing SMS credits."})
    reference = f"EDUSMS{secrets.token_hex(12).upper()}"
    callback_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/app/sms?reference={reference}"
    if not settings.DEBUG and not callback_url.startswith("https://"):
        raise ValidationError({"callback_url": "SMS checkout requires a secure HTTPS callback URL in production."})
    payment = SMSPurchase.objects.create(
        school=school, bundle=bundle, bundle_name=bundle.name, credits=bundle.credits,
        amount_minor=bundle.price_minor, provider=provider_name, reference=reference,
        customer_email=email, created_by=user,
    )
    try:
        arguments = {"email": email, "amount_minor": bundle.price_minor, "reference": reference, "callback_url": callback_url}
        if provider_name == SMSPurchase.Provider.FLUTTERWAVE:
            arguments.update(title="EDUstacked SMS", description=f"{bundle.name} SMS credit bundle")
        checkout = provider.initialize(**arguments)
    except Exception:
        payment.status = SMSPurchase.Status.FAILED
        payment.save(update_fields=("status", "updated_at"))
        raise
    authorization_url = checkout.get("authorization_url", "")
    if not authorization_url.startswith("https://"):
        payment.status = SMSPurchase.Status.FAILED
        payment.save(update_fields=("status", "updated_at"))
        raise ValidationError({"payment": "The payment provider did not return a secure checkout link."})
    payment.authorization_url = authorization_url
    payment.provider_metadata = {"checkout_id": checkout.get("id", "")}
    payment.provider_transaction_id = str(checkout.get("id", ""))
    payment.save(update_fields=("authorization_url", "provider_metadata", "provider_transaction_id", "updated_at"))
    return payment


@transaction.atomic
def apply_sms_purchase_result(payment, data):
    payment = SMSPurchase.objects.select_for_update().select_related("school").get(pk=payment.pk)
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        amount = -1
    if data.get("reference") != payment.reference:
        raise ValidationError({"payment": "The payment reference did not match this SMS purchase."})
    if data.get("status") == "success":
        if amount != payment.amount_minor or data.get("currency") != payment.currency:
            raise ValidationError({"payment": "Verified payment amount or currency did not match this SMS purchase."})
        if payment.status != SMSPurchase.Status.SUCCESS:
            School.objects.select_for_update().get(pk=payment.school_id)
            wallet, _ = SMSWallet.objects.get_or_create(school_id=payment.school_id)
            wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.purchased_balance += payment.credits
            wallet.paid_value_balance_minor += payment.amount_minor
            wallet.save(update_fields=("purchased_balance", "paid_value_balance_minor", "updated_at"))
            SMSWalletTransaction.objects.create(
                school_id=payment.school_id, kind=SMSWalletTransaction.Kind.PURCHASE,
                credits=payment.credits, description=f"Verified SMS bundle purchase: {payment.bundle_name}",
                reference_key=f"sms-purchase:{payment.reference}", purchase=payment,
                actor=None, unit_sale_price_minor=payment.amount_minor // payment.credits,
                metadata={"provider": payment.provider, "provider_transaction_id": str(data.get("id", "")), "amount_minor": payment.amount_minor},
            )
        payment.status = SMSPurchase.Status.SUCCESS
        payment.paid_at = timezone.now()
        payment.provider_transaction_id = str(data.get("id", payment.provider_transaction_id))
        payment.save(update_fields=("status", "paid_at", "provider_transaction_id", "updated_at"))
    elif data.get("status") in {"failed", "abandoned", "cancelled", "canceled"}:
        if payment.status == SMSPurchase.Status.PENDING:
            payment.status = SMSPurchase.Status.FAILED
            payment.save(update_fields=("status", "updated_at"))
    return payment


def verify_sms_purchase(payment, *, transaction_id=""):
    provider = _provider_instance(payment.provider)
    if payment.provider == SMSPurchase.Provider.PAYSTACK:
        data = provider.verify(payment.reference)
    else:
        transaction_id = transaction_id or payment.provider_transaction_id
        if not transaction_id:
            raise ValidationError({"payment": "The payment provider transaction ID is missing. Reopen checkout or contact support."})
        data = provider.verify(transaction_id)
    return apply_sms_purchase_result(payment, data)
