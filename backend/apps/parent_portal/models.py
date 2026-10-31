from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.schools.models import School
from apps.students.models import Guardian, Student, StudentGuardian


class GuardianInvitation(models.Model):
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="portal_invitations")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guardian_invitations_sent")
    email_snapshot = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="guardian_invitations_accepted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("guardian", "expires_at"), name="portal_invite_guardian_idx")]


class Announcement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="parent_announcements")
    title = models.CharField(max_length=180)
    message = models.TextField(max_length=10000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="parent_announcements_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="parent_announcements_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-published_at", "-id")
        indexes = [models.Index(fields=("school", "status", "published_at"), name="portal_announce_scope_idx")]
        constraints = [models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(published_at__isnull=True) | Q(expires_at__gt=models.F("published_at")), name="portal_announcement_expiry_after_publish")]

    def clean(self):
        super().clean()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            raise ValidationError({"published_at": "Published announcements require a publication date."})
        if self.expires_at and self.published_at and self.expires_at <= self.published_at:
            raise ValidationError({"expires_at": "Expiry must be later than publication."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PortalNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_portal_notifications")
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.CASCADE, related_name="parent_portal_notifications")
    announcement = models.ForeignKey(Announcement, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    event_key = models.CharField(max_length=180)
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=180)
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("user", "event_key"), name="portal_notification_event_user_uniq")]
        indexes = [models.Index(fields=("user", "read_at", "created_at"), name="portal_notification_user_idx")]


class PortalAuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="parent_portal_audit_events")
    guardian = models.ForeignKey(Guardian, null=True, blank=True, on_delete=models.PROTECT, related_name="portal_audit_events")
    student_link = models.ForeignKey(StudentGuardian, null=True, blank=True, on_delete=models.PROTECT, related_name="portal_audit_events")
    action = models.CharField(max_length=40)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Parent portal audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Parent portal audit events cannot be deleted.")
