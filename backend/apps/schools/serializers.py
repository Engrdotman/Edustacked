from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.accounts.serializers import SchoolMembershipSerializer
from .models import School, SchoolMembership

User = get_user_model()

ASSIGNABLE_ROLES = tuple(
    (role, label)
    for role, label in SchoolMembership.Role.choices
    if role != SchoolMembership.Role.MEMBER
)


class SchoolCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ("id", "name", "slug", "contact_email", "contact_phone", "address")
        read_only_fields = ("id",)
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}


class SchoolSelectionSerializer(serializers.Serializer):
    school_id = serializers.IntegerField()


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
                **validated_data,
            )

        membership = SchoolMembership.objects.create(
            user=user,
            school=school,
            role=role,
        )
        if is_new_user:
            from apps.accounts.emailing import send_password_setup_email

            transaction.on_commit(lambda: send_password_setup_email(user))
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
        return attrs
