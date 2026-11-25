"""Password setup/reset delivery without writing credentials or tokens to logs."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage, send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from datetime import timedelta
from hashlib import sha256
from urllib.parse import urlencode
import secrets
import logging


logger = logging.getLogger(__name__)


def _send_password_action_email(user, *, action, school_name="", fail_silently=True):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = (
        f"{settings.PASSWORD_RESET_FRONTEND_URL}/reset-password?"
        f"{urlencode({'uid': uid, 'token': token})}"
    )
    is_reset = action == "reset"
    subject = "Reset your EDUstacked password" if is_reset else "Set up your EDUstacked account"
    template_id = getattr(settings, "SENDGRID_PASSWORD_SETUP_TEMPLATE_ID", "")
    if template_id and settings.EMAIL_BACKEND.endswith("SendgridBackend"):
        message = EmailMessage(subject, "Use the secure link to set your password.", settings.DEFAULT_FROM_EMAIL, [user.email])
        message.dynamic_template_id = template_id
        message.dynamic_template_data = {
            # Keep the original key for existing SendGrid templates; new templates
            # should use password_reset_url (or action_url) for their CTA link.
            "password_setup_url": reset_url,
            "password_reset_url": reset_url,
            "reset_password_url": reset_url,
            "action_url": reset_url,
            "email_purpose": "password_reset" if is_reset else "password_setup",
            "action_heading": "Set a new password" if is_reset else "Set up your password",
            "action_message": (
                "We received a request to reset your EDUstacked password."
                if is_reset else "Set a password to finish setting up your EDUstacked account."
            ),
            "action_button": "Set new password" if is_reset else "Set up account",
            "first_name": user.first_name,
            "full_name": user.get_full_name().strip() or user.email,
            "school_name": school_name,
        }
        return message.send(fail_silently=fail_silently)
    return send_mail(
        subject=subject,
        message=(
            ("Use this secure link to reset your EDUstacked password. " if is_reset else "Use this secure link to set up your EDUstacked password. ")
            +
            f"The link expires after {settings.PASSWORD_RESET_TIMEOUT // 60} minutes:\n\n"
            f"{reset_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=fail_silently,
    )


def send_password_setup_email(user, *, school_name="", fail_silently=True):
    return _send_password_action_email(
        user, action="setup", school_name=school_name, fail_silently=fail_silently,
    )


def send_password_reset_email(user, *, fail_silently=True):
    return _send_password_action_email(user, action="reset", fail_silently=fail_silently)


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


def send_demo_request_notification(demo_request):
    """Alert EDUstacked about a public demo or assisted-onboarding request."""
    recipient = getattr(settings, "PLATFORM_DEMO_REQUEST_NOTIFICATION_EMAIL", "").strip()
    if not recipient:
        logger.error("Platform demo request notification email is not configured.")
        return "failed"

    subject = f"New EDUstacked demo or onboarding request: {demo_request.school_name}"
    request_message = demo_request.message.strip() or "No additional details provided."
    body = (
        "A new product demo or assisted-onboarding request was submitted.\n\n"
        f"Request ID: {demo_request.pk}\n"
        f"School: {demo_request.school_name}\n"
        f"Administrator: {demo_request.administrator_name}\n"
        f"Email: {demo_request.email}\n"
        f"Phone: {demo_request.phone_number}\n"
        f"Request details:\n{request_message}\n\n"
        f"Received: {demo_request.created_at.isoformat()}\n"
    )
    template_id = getattr(settings, "SENDGRID_DEMO_REQUEST_NOTIFICATION_TEMPLATE_ID", "")
    try:
        if template_id and settings.EMAIL_BACKEND.endswith("SendgridBackend"):
            message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
            message.dynamic_template_id = template_id
            message.dynamic_template_data = {
                "request_id": demo_request.pk,
                "school_name": demo_request.school_name,
                "administrator_name": demo_request.administrator_name,
                "requester_email": demo_request.email,
                "phone_number": demo_request.phone_number,
                "request_message": request_message,
                "received_at": demo_request.created_at.isoformat(),
                "support_email": settings.DEFAULT_FROM_EMAIL,
            }
            sent = message.send(fail_silently=False)
        else:
            sent = send_mail(
                subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False
            )
    except Exception:
        logger.exception("Platform demo request notification delivery failed.")
        return "failed"

    if not sent:
        logger.error("Platform demo request notification was not accepted by the email backend.")
        return "failed"
    if settings.EMAIL_BACKEND.endswith(("locmem.EmailBackend", "console.EmailBackend", "filebased.EmailBackend")):
        return "local_only"
    return "sent"


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
