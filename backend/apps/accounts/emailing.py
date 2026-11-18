"""Password setup/reset delivery without writing credentials or tokens to logs."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage, send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from datetime import timedelta
from hashlib import sha256
import secrets
import logging


logger = logging.getLogger(__name__)


def send_password_setup_email(user, *, school_name="", fail_silently=True):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"
    subject = "Set up your EDUstacked account"
    template_id = getattr(settings, "SENDGRID_PASSWORD_SETUP_TEMPLATE_ID", "")
    if template_id and settings.EMAIL_BACKEND.endswith("SendgridBackend"):
        message = EmailMessage(subject, "Use the secure link to set up your account.", settings.DEFAULT_FROM_EMAIL, [user.email])
        message.dynamic_template_id = template_id
        message.dynamic_template_data = {
            "password_setup_url": reset_url,
            "first_name": user.first_name,
            "full_name": user.get_full_name().strip() or user.email,
            "school_name": school_name,
        }
        return message.send(fail_silently=fail_silently)
    return send_mail(
        subject=subject,
        message=(
            "Use this secure link to set or reset your password. "
            f"The link expires after {settings.PASSWORD_RESET_TIMEOUT // 60} minutes:\n\n"
            f"{reset_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=fail_silently,
    )


def issue_email_verification(user):
    from .models import EmailVerificationToken

    now = timezone.now()
    EmailVerificationToken.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=now)
    secret = secrets.token_urlsafe(32)
    token = EmailVerificationToken.objects.create(
        user=user,
        token_hash=sha256(secret.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(seconds=getattr(settings, "EMAIL_VERIFICATION_TIMEOUT", 86400)),
    )
    return token, secret


def send_email_verification(user, selector, secret, *, school_name="", fail_silently=True):
    verification_url = (
        f"{settings.FRONTEND_BASE_URL}/verify-email?selector={selector}&token={secret}"
    )
    subject = "Verify your EDUstacked email address"
    body = (
        "Verify your email address to activate access to your school workspace. "
        f"This one-time link expires after {getattr(settings, 'EMAIL_VERIFICATION_TIMEOUT', 86400) // 3600} hours:\n\n"
        f"{verification_url}\n"
    )
    template_id = getattr(settings, "SENDGRID_VERIFICATION_TEMPLATE_ID", "")
    if template_id and settings.EMAIL_BACKEND.endswith("SendgridBackend"):
        message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        message.dynamic_template_id = template_id
        message.dynamic_template_data = {
            "verification_url": verification_url,
            "first_name": user.first_name,
            "full_name": user.get_full_name().strip() or user.email,
            "school_name": school_name,
        }
        return message.send(fail_silently=fail_silently)
    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=fail_silently)


def send_school_signup_notification(school, owner):
    """Notify EDUstacked when a school workspace is registered; never block signup."""
    recipient = getattr(settings, "PLATFORM_SIGNUP_NOTIFICATION_EMAIL", "").strip()
    if not recipient:
        return 0

    subject = f"New school registration: {school.name}"
    review_url = f"{settings.FRONTEND_BASE_URL}/platform/schools"
    admin_name = owner.get_full_name().strip() or owner.email
    body = (
        "A new school workspace has been registered on EDUstacked.\n\n"
        f"School: {school.name}\n"
        f"Administrator: {admin_name}\n"
        f"Administrator email: {owner.email}\n"
        f"School email: {school.contact_email or 'Not provided'}\n"
        f"School phone: {school.contact_phone or 'Not provided'}\n"
        f"Location: {', '.join(value for value in (school.local_government_area, school.state, school.country) if value) or 'Not provided'}\n"
        f"School type: {school.get_school_type_display()}\n"
        f"Registration status: {school.get_verification_status_display()}\n"
        f"Registered at: {school.created_at.isoformat()}\n\n"
        f"Review registrations: {review_url}\n"
    )
    template_id = getattr(settings, "SENDGRID_SCHOOL_SIGNUP_NOTIFICATION_TEMPLATE_ID", "")
    try:
        if template_id and settings.EMAIL_BACKEND.endswith("SendgridBackend"):
            message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
            message.dynamic_template_id = template_id
            message.dynamic_template_data = {
                "school_name": school.name,
                "administrator_name": admin_name,
                "administrator_email": owner.email,
                "school_email": school.contact_email or "",
                "school_phone": school.contact_phone or "",
                "school_type": school.get_school_type_display(),
                "country": school.country,
                "state": school.state,
                "local_government_area": school.local_government_area,
                "verification_status": school.get_verification_status_display(),
                "registered_at": school.created_at.isoformat(),
                "review_url": review_url,
            }
            return message.send(fail_silently=False)
        return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
    except Exception:
        # Signup has already committed; a provider outage must not make the new
        # owner think registration failed. Keep the delivery failure observable.
        logger.exception("Platform school signup notification delivery failed.")
        return 0


def send_staff_invitation_emails(user, verification=None, *, school_name=""):
    """Send needed staff access emails and report delivery without losing the membership."""
    statuses = {}
    jobs = []
    if not user.has_usable_password():
        jobs.append(("password_setup", lambda: send_password_setup_email(user, school_name=school_name, fail_silently=False)))
    if user.email_verified_at is None and verification:
        selector, secret = verification
        jobs.append(("email_verification", lambda: send_email_verification(user, selector, secret, school_name=school_name, fail_silently=False)))

    if not jobs:
        return {"password_setup": "not_needed", "email_verification": "not_needed"}

    if settings.EMAIL_BACKEND.endswith(("locmem.EmailBackend", "console.EmailBackend", "filebased.EmailBackend")):
        return {name: "local_only" for name, _ in jobs} | {
            name: "not_needed" for name in ("password_setup", "email_verification")
            if name not in {job_name for job_name, _ in jobs}
        }

    for name, send in jobs:
        try:
            statuses[name] = "accepted" if send() == 1 else "failed"
        except Exception:
            logger.exception("Staff invitation email delivery failed (%s).", name)
            statuses[name] = "failed"
    for name in ("password_setup", "email_verification"):
        statuses.setdefault(name, "not_needed")
    return statuses
