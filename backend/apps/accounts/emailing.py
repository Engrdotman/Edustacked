"""Password setup/reset delivery without writing credentials or tokens to logs."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


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
