from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.students.models import Guardian

from .models import Announcement, PortalNotification


class GuardianProfileSerializer(serializers.ModelSerializer):
    schools = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "schools")
        read_only_fields = ("email", "schools")

    def get_schools(self, user):
        guardian_records = Guardian.objects.filter(
            user=user, is_active=True, school__is_active=True,
            student_links__is_active=True,
        ).select_related("school").distinct()
        return [{"id": record.school_id, "name": record.school.name, "guardian_name": record.full_name} for record in guardian_records]


class GuardianActivationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=160, trim_whitespace=False)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class AnnouncementSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Announcement
        fields = ("id", "school", "school_name", "title", "message", "status", "published_at", "expires_at", "created_at", "updated_at")
        read_only_fields = ("school", "school_name", "status", "published_at", "created_at", "updated_at")

    def validate(self, attrs):
        expires = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        published = getattr(self.instance, "published_at", None)
        if expires and published and expires <= published:
            raise serializers.ValidationError({"expires_at": "Expiry must be later than publication."})
        return attrs


class AnnouncementParentSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Announcement
        fields = ("id", "school_name", "title", "message", "published_at", "expires_at")


class PortalNotificationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = PortalNotification
        fields = ("id", "kind", "title", "message", "student", "student_name", "announcement", "created_at", "read_at")

    def get_student_name(self, obj):
        return obj.student.get_full_name() if obj.student_id else ""
