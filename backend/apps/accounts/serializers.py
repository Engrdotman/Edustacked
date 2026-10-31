import hashlib
import re
from uuid import uuid4

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.schools.models import School, SchoolMembership

User = get_user_model()


class SchoolSignupSerializer(serializers.Serializer):
    school_name = serializers.CharField(max_length=200, trim_whitespace=True)
    administrator_name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)
    password_confirmation = serializers.CharField(write_only=True, trim_whitespace=False)
    school_email = serializers.EmailField(required=False, allow_blank=True)
    school_phone = serializers.CharField(max_length=30)
    school_type = serializers.ChoiceField(choices=School.SchoolType.choices)
    country = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    local_government_area = serializers.CharField(max_length=120)
    address = serializers.CharField(max_length=2000)

    def validate_phone_number(self, value):
        if not re.fullmatch(r"\+?[0-9][0-9 ()-]{6,28}", value.strip()):
            raise serializers.ValidationError("Enter a valid phone number, including country code when possible.")
        return value.strip()

    validate_school_phone = validate_phone_number

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Registration could not be completed with these details. Contact support if needed.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({"password_confirmation": "The passwords do not match."})
        attrs["country"] = attrs["country"].strip()
        attrs["state"] = attrs["state"].strip()
        attrs["local_government_area"] = attrs["local_government_area"].strip()
        if not all(attrs[key] for key in ("country", "state", "local_government_area")):
            raise serializers.ValidationError("Country, state, and local government area are required.")
        attrs["school_email"] = attrs.get("school_email", "").strip().lower()
        location_key = "|".join((
            " ".join(attrs["school_name"].casefold().split()),
            attrs["country"].casefold(), attrs["state"].casefold(), attrs["local_government_area"].casefold(),
        ))
        attrs["registration_key"] = hashlib.sha256(location_key.encode("utf-8")).hexdigest()
        if School.objects.filter(registration_key=attrs["registration_key"]).exists():
            raise serializers.ValidationError("A school with these registration details already exists. Contact support if you believe this is an error.")
        first_name, *last_name = attrs["administrator_name"].split(maxsplit=1)
        prospective_user = User(
            username=attrs["email"].split("@", 1)[0],
            email=attrs["email"],
            first_name=first_name,
            last_name=last_name[0] if last_name else "",
        )
        try:
            validate_password(attrs["password"], user=prospective_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        school_name = validated_data["school_name"]
        admin_name = validated_data["administrator_name"].split(maxsplit=1)
        email = validated_data["email"]
        from .emailing import issue_email_verification, send_email_verification

        base_slug = slugify(school_name)[:180] or "school"
        slug = f"{base_slug}-{uuid4().hex[:8]}"
        username = f"{email.split('@', 1)[0][:140]}-{uuid4().hex[:8]}"
        school = School.objects.create(
            name=school_name,
            slug=slug,
            contact_email=validated_data["school_email"],
            contact_phone=validated_data["school_phone"],
            school_type=validated_data["school_type"],
            country=validated_data["country"],
            state=validated_data["state"],
            local_government_area=validated_data["local_government_area"],
            address=validated_data["address"],
            registration_key=validated_data["registration_key"],
        )
        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data["password"],
            first_name=admin_name[0],
            last_name=admin_name[1] if len(admin_name) > 1 else "",
            phone_number=validated_data["phone_number"],
            email_verified_at=None,
        )
        SchoolMembership.objects.create(
            school=school, user=user, role=SchoolMembership.Role.SCHOOL_OWNER,
        )
        token, secret = issue_email_verification(user)
        transaction.on_commit(lambda user=user, selector=token.selector, secret=secret: send_email_verification(user, selector, secret))
        return school


class EmailVerificationSerializer(serializers.Serializer):
    selector = serializers.UUIDField()
    token = serializers.CharField(trim_whitespace=False, max_length=100)


class ResendEmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class DemoRequestSerializer(serializers.Serializer):
    administrator_name = serializers.CharField(max_length=150, trim_whitespace=True)
    school_name = serializers.CharField(max_length=200, trim_whitespace=True)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=30)
    message = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate_phone_number(self, value):
        if not re.fullmatch(r"\+?[0-9][0-9 ()-]{6,28}", value.strip()):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value.strip()

    def create(self, validated_data):
        from .models import DemoRequest
        validated_data["email"] = validated_data["email"].strip().lower()
        return DemoRequest.objects.create(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if user.email_verified_at is None:
            raise serializers.ValidationError({"email": "Please verify your email address before signing in."})
        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    email_verified = serializers.SerializerMethodField()
    phone_verified = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "is_active", "is_superuser", "email_verified", "phone_number", "phone_verified")
        read_only_fields = fields

    def get_email_verified(self, obj):
        return obj.email_verified_at is not None

    def get_phone_verified(self, obj):
        return obj.phone_verified_at is not None


class SchoolMembershipSerializer(serializers.ModelSerializer):
    school_id = serializers.IntegerField(source="school.pk", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_slug = serializers.CharField(source="school.slug", read_only=True)
    school_verification_status = serializers.CharField(source="school.verification_status", read_only=True)
    school_verification_reason = serializers.CharField(source="school.verification_reason", read_only=True)
    school_accessible = serializers.SerializerMethodField()
    user_email_verified = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = SchoolMembership
        fields = (
            "id",
            "school_id",
            "school_name",
            "school_slug",
            "school_verification_status",
            "school_verification_reason",
            "school_accessible",
            "user_email_verified",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
        )
        read_only_fields = fields

    def get_school_accessible(self, obj):
        return obj.school.is_active and obj.school.verification_status != obj.school.VerificationStatus.SUSPENDED

    def get_user_email_verified(self, obj):
        return obj.user.email_verified_at is not None


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value
