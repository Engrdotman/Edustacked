import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from apps.students.models import Guardian, Student, StudentGuardian

from .models import GuardianInvitation, PortalAuditEvent, PortalNotification

User = get_user_model()


def guardian_records_for_user(user):
    return Guardian.objects.filter(user=user, is_active=True, school__is_active=True)


def linked_student_queryset(user):
    return Student.objects.filter(
        guardian_links__guardian__in=guardian_records_for_user(user),
        guardian_links__is_active=True,
    ).distinct()


def schools_for_user(user):
    return guardian_records_for_user(user).filter(
        student_links__is_active=True,
        student_links__can_receive_communications=True,
    ).values_list("school_id", flat=True).distinct()


def notify_guardians_for_student(student, event_key, kind, title, message, *, announcement=None):
    guardian_ids = StudentGuardian.objects.filter(
        school=student.school, student=student, is_active=True,
        can_receive_communications=True, guardian__is_active=True,
        guardian__user__isnull=False,
    ).values_list("guardian__user_id", flat=True).distinct()
    for user_id in guardian_ids:
        PortalNotification.objects.get_or_create(
            user_id=user_id, event_key=event_key,
            defaults={"student": student, "announcement": announcement,
                      "kind": kind, "title": title, "message": message},
        )


@transaction.atomic
def issue_guardian_invitation(link, actor):
    guardian = Guardian.objects.select_for_update().get(pk=link.guardian_id)
    email = guardian.email.strip().lower()
    if not guardian.is_active or not link.is_active:
        raise ValidationError("Only an active guardian-student link can be invited.")
    if not email:
        raise ValidationError({"email": "Add the guardian's email to the school record before inviting them."})
    if guardian.user_id:
        raise ValidationError({"guardian": "This guardian already has portal access."})
    now = timezone.now()
    GuardianInvitation.objects.filter(
        guardian=guardian, accepted_at__isnull=True, revoked_at__isnull=True,
        expires_at__gt=now,
    ).update(revoked_at=now)
    token = secrets.token_urlsafe(40)
    invitation = GuardianInvitation.objects.create(
        guardian=guardian, invited_by=actor, email_snapshot=email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT),
    )
    activation_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/guardian/activate?token={token}"
    try:
        sent = send_mail(
            subject=f"Activate your {guardian.school.name} parent portal",
            message=(
                f"Hello {guardian.full_name},\n\n"
                "Your school invited you to the EDUstacked parent portal. "
                f"Activate access within {settings.PASSWORD_RESET_TIMEOUT // 60} minutes using this one-time link:\n\n"
                f"{activation_url}\n\nIf you were not expecting this invitation, contact the school."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email], fail_silently=False,
        )
    except Exception as exc:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=("revoked_at",))
        raise ValidationError({"email": "The invitation email could not be sent. Check the school's email configuration and retry."}) from exc
    if sent != 1:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=("revoked_at",))
        raise ValidationError({"email": "The invitation email could not be sent. Check the school's email configuration and retry."})
    PortalAuditEvent.objects.create(
        actor=actor, guardian=guardian, student_link=link,
        action="guardian_invitation_sent", metadata={"delivery": "email"},
    )
    return invitation


@transaction.atomic
def activate_guardian_invitation(raw_token, password):
    if not raw_token or len(raw_token) > 160:
        raise ValidationError({"token": "This invitation is invalid or expired."})
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    try:
        invitation = GuardianInvitation.objects.select_for_update().select_related("guardian").get(token_hash=token_hash)
    except GuardianInvitation.DoesNotExist:
        raise ValidationError({"token": "This invitation is invalid or expired."}) from None
    now = timezone.now()
    guardian = Guardian.objects.select_for_update().get(pk=invitation.guardian_id)
    if (
        invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= now
        or not guardian.is_active or guardian.email.strip().lower() != invitation.email_snapshot
        or not StudentGuardian.objects.filter(guardian=guardian, school=guardian.school, is_active=True).exists()
    ):
        raise ValidationError({"token": "This invitation is invalid or expired."})
    email = invitation.email_snapshot
    user = User.objects.filter(login_email__iexact=email).first()
    created = user is None
    if created:
        try:
            validate_password(password)
        except ValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from exc
        name_parts = guardian.full_name.strip().split(maxsplit=1)
        user = User.objects.create_user(
            username=f"guardian_{secrets.token_hex(12)}", email=email, password=password,
            first_name=name_parts[0] if name_parts else "", last_name=name_parts[1] if len(name_parts) > 1 else "",
        )
    elif not user.is_active or not user.check_password(password):
        raise ValidationError({"password": "Use the password for the existing EDUstacked account associated with this email."})
    if guardian.user_id and guardian.user_id != user.pk:
        raise ValidationError({"token": "This invitation is invalid or expired."})
    guardian.user = user
    guardian.save(update_fields=("user", "updated_at"))
    invitation.accepted_at = now
    invitation.accepted_by = user
    invitation.save(update_fields=("accepted_at", "accepted_by"))
    PortalAuditEvent.objects.create(
        actor=user, guardian=guardian, action="guardian_invitation_accepted",
        metadata={"account_created": created},
    )
    PortalNotification.objects.get_or_create(
        user=user, event_key=f"guardian-portal:activated:{invitation.pk}",
        defaults={"kind": "portal_activated", "title": "Parent portal activated",
                  "message": f"You can now view students linked to {guardian.school.name}."},
    )
    return user
