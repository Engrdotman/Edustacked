"""Password setup/reset delivery without writing credentials or tokens to logs."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from datetime import timedelta
from hashlib import sha256
import secrets


def send_password_setup_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"
    return send_mail(
        subject="Set up your School Management account",
        message=(
            "Use this secure link to set or reset your password. "
            f"The link expires after {settings.PASSWORD_RESET_TIMEOUT // 60} minutes:\n\n"
            f"{reset_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
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


def send_email_verification(user, selector, secret):
    verification_url = (
        f"{settings.FRONTEND_BASE_URL}/verify-email?selector={selector}&token={secret}"
    )
    return send_mail(
        subject="Verify your EDUstacked email address",
        message=(
            "Verify your email address to activate access to your school workspace. "
            f"This one-time link expires after {getattr(settings, 'EMAIL_VERIFICATION_TIMEOUT', 86400) // 3600} hours:\n\n"
            f"{verification_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
