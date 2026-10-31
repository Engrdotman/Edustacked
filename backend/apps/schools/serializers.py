from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify
from pathlib import Path
from zoneinfo import available_timezones
from rest_framework import serializers

from apps.accounts.serializers import SchoolMembershipSerializer
from .models import MAX_SCHOOL_LOGO_SIZE, School, SchoolMembership, SchoolSettings

User = get_user_model()

ASSIGNABLE_ROLES = tuple(
    (role, label)
    for role, label in SchoolMembership.Role.choices
    if role not in {SchoolMembership.Role.MEMBER, SchoolMembership.Role.SCHOOL_OWNER}
)


class SchoolCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ("id", "name", "slug", "contact_email", "contact_phone", "address")
        read_only_fields = ("id",)
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}


class SchoolSelectionSerializer(serializers.Serializer):
    school_id = serializers.IntegerField()


class SchoolProfileSerializer(serializers.ModelSerializer):
    logo_present = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = (
            "id", "name", "slug", "logo_present", "contact_email", "contact_phone",
            "address", "state", "local_government_area", "website", "motto",
            "description", "is_active", "created_at", "updated_at",
            "school_type", "country", "verification_status", "verification_reason", "verified_at",
        )
        read_only_fields = ("id", "slug", "logo_present", "is_active", "verification_status", "verification_reason", "verified_at", "created_at", "updated_at")

    def get_logo_present(self, obj):
        return bool(obj.logo)


class SchoolLogoSerializer(serializers.Serializer):
    logo = serializers.ImageField()

    def validate_logo(self, value):
        if value.size > MAX_SCHOOL_LOGO_SIZE:
            raise serializers.ValidationError("School logos must be 2 MB or smaller.")
        image_format = getattr(value.image, "format", "").upper()
        extension = Path(value.name).suffix.lower()
        matching_extensions = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}
        if image_format not in matching_extensions or extension not in matching_extensions[image_format]:
            raise serializers.ValidationError("Use a JPG, PNG, or WebP image.")
        return value


class SchoolSettingsSerializer(serializers.ModelSerializer):
    time_zone = serializers.ChoiceField(choices=sorted(available_timezones()), required=False)

    class Meta:
        model = SchoolSettings
        fields = (
            "default_currency", "time_zone", "date_format", "academic_year_label",
            "contact_preferences", "branding_primary_color", "created_at", "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate_default_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha() or not value.isascii():
            raise serializers.ValidationError("Use a three-letter ISO currency code, such as NGN.")
        return value

    def validate_contact_preferences(self, value):
        if not isinstance(value, dict) or set(value) - {"email", "phone"}:
            raise serializers.ValidationError("Use email and/or phone boolean preferences.")
        if any(not isinstance(item, bool) for item in value.values()):
            raise serializers.ValidationError("Contact preference values must be true or false.")
        return value

    def validate_branding_primary_color(self, value):
        import re

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Enter a six-digit hex color, such as #285744.")
        return value.upper()


class MembershipProvisionSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=ASSIGNABLE_ROLES)

    def validate_email(self, value):
        email = value.strip().lower()
        school = self.context["school"]
        actor = self.context["request"].user
        if actor.login_email and email == actor.login_email:
            raise serializers.ValidationError("You cannot provision or change your own membership role.")

        existing_login = User.objects.filter(login_email=email).first()
        ambiguous_legacy = User.objects.filter(email__iexact=email).exclude(
            login_email=email
        ).exists()
        if ambiguous_legacy:
            raise serializers.ValidationError(
                "This email belongs to a legacy account that needs platform review."
            )
        if existing_login and SchoolMembership.objects.filter(
            user=existing_login, school=school
        ).exists():
            raise serializers.ValidationError("This user already has a membership in this school.")
        return email

    def validate(self, attrs):
        actor = self.context["request"].user
        if (
            not actor.is_superuser
            and attrs["role"] == SchoolMembership.Role.SCHOOL_ADMIN
        ):
            raise serializers.ValidationError(
                {"role": "Only a platform superadmin can assign the school admin role."}
            )
        if attrs["role"] == SchoolMembership.Role.SCHOOL_OWNER:
            raise serializers.ValidationError({"role": "Ownership can only be changed through the secure ownership transfer action."})
        return attrs

    @staticmethod
    def _available_username(email):
        stem = slugify(email.split("@", 1)[0])[:140] or "school-user"
        candidate = stem
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            candidate = f"{stem[:140 - len(str(suffix)) - 1]}-{suffix}"
            suffix += 1
        return candidate

    @transaction.atomic
    def create(self, validated_data):
        school = validated_data.pop("school")
        email = validated_data.pop("email")
        role = validated_data.pop("role")
        user = User.objects.filter(login_email=email).first()
        is_new_user = user is None
        if is_new_user:
            user = User.objects.create_user(
                username=self._available_username(email),
                email=email,
                password=None,
                is_active=True,
                email_verified_at=None,
                **validated_data,
            )

        membership = SchoolMembership.objects.create(
            user=user,
            school=school,
            role=role,
        )
        if is_new_user:
            from apps.accounts.emailing import issue_email_verification, send_email_verification, send_password_setup_email
            verification, secret = issue_email_verification(user)
            transaction.on_commit(lambda user=user: send_password_setup_email(user))
            transaction.on_commit(lambda user=user, selector=verification.selector, secret=secret: send_email_verification(user, selector, secret))
        return membership

    def to_representation(self, instance):
        return SchoolMembershipSerializer(instance, context=self.context).data


class MembershipAdminUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ASSIGNABLE_ROLES, required=False)

    class Meta:
        model = SchoolMembership
        fields = ("role", "is_active")

    def validate(self, attrs):
        request = self.context["request"]
        membership = self.instance
        if membership.role == SchoolMembership.Role.SCHOOL_OWNER:
            raise serializers.ValidationError("Transfer school ownership through the secure ownership transfer action.")
        if membership.user_id == request.user.pk:
            raise serializers.ValidationError("You cannot change or revoke your own membership.")
        if membership.user.is_superuser and not request.user.is_superuser:
            raise serializers.ValidationError("Only a platform superadmin can manage this account.")
        if (
            attrs.get("role") == SchoolMembership.Role.SCHOOL_ADMIN
            and not request.user.is_superuser
        ):
            raise serializers.ValidationError(
                {"role": "Only a platform superadmin can assign the school admin role."}
            )
        if attrs.get("role") == SchoolMembership.Role.SCHOOL_OWNER:
            raise serializers.ValidationError({"role": "Ownership can only be changed through the secure ownership transfer action."})
        return attrs
