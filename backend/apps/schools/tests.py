from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from io import BytesIO
from tempfile import TemporaryDirectory
import random
from PIL import Image

from .models import School, SchoolMembership
from .permissions import HasSchoolPermission
from .tenancy import SchoolScopedQuerySetMixin, authorized_schools_for
from .views import SchoolCreateView, SchoolMembershipDetailView, SchoolMembershipListCreateView

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = SchoolMembership
        fields = ("id", "school", "user", "role")


class MembershipCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolMembership
        fields = ("id", "school", "user", "role")


class MembershipListView(SchoolScopedQuerySetMixin, ListAPIView):
    queryset = SchoolMembership.objects.select_related("school", "user")
    serializer_class = MembershipSerializer


class MembershipListCreateView(SchoolScopedQuerySetMixin, ListCreateAPIView):
    queryset = SchoolMembership.objects.select_related("school", "user")
    serializer_class = MembershipCreateSerializer


class MembershipDetailView(SchoolScopedQuerySetMixin, RetrieveAPIView):
    queryset = SchoolMembership.objects.select_related("school", "user")
    serializer_class = MembershipSerializer


urlpatterns = [path("schools/<str:school_id>/memberships/", MembershipListView.as_view())]


def role_probe(permission_name):
    def get(self, request):
        return Response({"granted": True})

    return type(
        "RoleProbeView",
        (APIView,),
        {
            "permission_classes": (IsAuthenticated, HasSchoolPermission),
            "required_school_permission": permission_name,
            "get": get,
        },
    ).as_view()


class SchoolModelTests(TestCase):
    def test_school_saves_with_slug_from_name_and_optional_contact_details(self):
        school = School.objects.create(name="Lagos Model School")

        self.assertTrue(school.pk)
        self.assertEqual(school.slug, "lagos-model-school")
        self.assertEqual(school.contact_email, "")
        self.assertEqual(school.contact_phone, "")
        self.assertEqual(school.address, "")

    def test_school_full_clean_generates_slug_and_rejects_duplicate(self):
        first = School(name="Unity Academy")
        first.full_clean()
        self.assertEqual(first.slug, "unity-academy")
        first.save()

        duplicate = School(name="Another School", slug="unity-academy")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

        invalid_contact = School(name="Contact Test", contact_email="not-an-email")
        with self.assertRaises(ValidationError):
            invalid_contact.full_clean()

    def test_database_enforces_unique_slug(self):
        School.objects.create(name="First School", slug="shared-code")
        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="Second School", slug="shared-code")

    def test_database_rejects_empty_school_name_and_slug(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="", slug="")


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolMembershipTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="school-user", password="test")
        self.other_user = User.objects.create_user(username="other-user", password="test")
        self.school = School.objects.create(name="North School")
        self.other_school = School.objects.create(name="South School")
        self.membership = SchoolMembership.objects.create(
            user=self.user, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.other_membership = SchoolMembership.objects.create(
            user=self.other_user, school=self.other_school
        )

    def test_membership_relationship_and_unique_user_school_constraint(self):
        self.assertEqual(self.user.school_memberships.get(), self.membership)
        self.assertEqual(self.school.memberships.get(), self.membership)

        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolMembership.objects.create(user=self.user, school=self.school)

    def test_user_can_belong_to_multiple_schools(self):
        second_school = School.objects.create(name="West School")
        second_membership = SchoolMembership.objects.create(
            user=self.user, school=second_school
        )

        self.assertEqual(self.user.school_memberships.count(), 2)
        self.assertEqual(second_membership.school, second_school)

        request = APIRequestFactory().get("/schools/")
        force_authenticate(request, user=self.user)
        response = MembershipListView.as_view()(request, school_id=str(second_school.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_membership_rejects_unknown_role(self):
        membership = SchoolMembership(
            user=self.user, school=self.other_school, role="unknown_role"
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolMembership.objects.create(
                user=self.other_user,
                school=School.objects.create(name="Temporary School"),
                role="unknown_role",
            )

    def test_authorized_school_queryset_excludes_inactive_and_unrelated_schools(self):
        inactive_membership_school = School.objects.create(
            name="Inactive School", is_active=False
        )
        SchoolMembership.objects.create(user=self.user, school=inactive_membership_school)
        SchoolMembership.objects.create(
            user=self.user, school=self.other_school, is_active=False
        )

        self.assertEqual(list(authorized_schools_for(self.user)), [self.school])
        self.assertFalse(authorized_schools_for(AnonymousUser()).exists())

    def test_tenant_scoped_view_returns_only_requested_authorized_school(self):
        factory = APIRequestFactory()
        request = factory.get(f"/schools/{self.school.pk}/memberships/")
        force_authenticate(request, user=self.user)

        response = MembershipListView.as_view()(request, school_id=str(self.school.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["school"] for row in response.data], [self.school.pk])

    def test_foreign_inactive_or_missing_tenant_context_returns_404(self):
        factory = APIRequestFactory()
        view = MembershipListView.as_view()
        inactive_school = School.objects.create(name="Inactive School", is_active=False)
        SchoolMembership.objects.create(user=self.user, school=inactive_school)
        restricted_user = User.objects.create_user(username="inactive-member", password="test")
        SchoolMembership.objects.create(
            user=restricted_user, school=self.other_school, is_active=False
        )

        for school_id in (
            str(self.other_school.pk),
            str(inactive_school.pk),
            "999999",
            "not-an-id",
        ):
            request = factory.get("/schools/")
            force_authenticate(request, user=self.user)
            response = view(request, school_id=school_id)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        request = factory.get("/schools/")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        request = factory.get("/schools/")
        force_authenticate(request, user=self.other_user)
        response = view(request, school_id=str(self.school.pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        request = factory.get("/schools/")
        force_authenticate(request, user=restricted_user)
        response = view(request, school_id=str(self.other_school.pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_object_lookup_cannot_retrieve_membership_from_another_school(self):
        request = APIRequestFactory().get("/schools/")
        force_authenticate(request, user=self.user)

        response = MembershipDetailView.as_view()(
            request,
            school_id=str(self.school.pk),
            pk=self.other_membership.pk,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_client_supplied_school_is_overridden_on_create(self):
        new_user = User.objects.create_user(username="new-user", password="test")
        factory = APIRequestFactory()
        request = factory.post("/schools/", {
            "school": self.other_school.pk,
            "user": new_user.pk,
            "role": SchoolMembership.Role.MEMBER,
        }, format="json")
        force_authenticate(request, user=self.user)

        response = MembershipListCreateView.as_view()(
            request, school_id=str(self.school.pk)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = SchoolMembership.objects.get(user=new_user, school=self.school)
        self.assertEqual(created.school, self.school)


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolRoleApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Role Test School")
        self.other_school = School.objects.create(name="Other Role School")
        self.factory = APIRequestFactory()

    def user_with_role(self, role, username=None, school=None):
        username = username or f"user-{role}"
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="Strong-Test-Pass-284!",
        )
        SchoolMembership.objects.create(
            user=user,
            school=school or self.school,
            role=role,
        )
        return user

    def request_permission(self, user, school, permission_name):
        request = self.factory.get("/api/v1/probe/", HTTP_X_SCHOOL_ID=str(school.pk))
        force_authenticate(request, user=user)
        return role_probe(permission_name)(request)

    def test_role_permission_matrix_is_enforced_by_drf_api_permissions(self):
        cases = (
            (SchoolMembership.Role.SCHOOL_ADMIN, "finance.manage", True),
            (SchoolMembership.Role.SCHOOL_MANAGER, "results.enter", True),
            (SchoolMembership.Role.SCHOOL_MANAGER, "results.approve", False),
            (SchoolMembership.Role.TEACHER, "results.enter", True),
            (SchoolMembership.Role.TEACHER, "finance.view", False),
            (SchoolMembership.Role.ACCOUNTANT, "finance.manage", True),
            (SchoolMembership.Role.ACCOUNTANT, "results.enter", False),
            (SchoolMembership.Role.RECEPTIONIST, "frontdesk.manage", True),
            (SchoolMembership.Role.RECEPTIONIST, "attendance.manage", False),
            (SchoolMembership.Role.MEMBER, "students.view", False),
        )
        for index, (role, permission_name, expected) in enumerate(cases):
            with self.subTest(role=role, permission=permission_name):
                user = self.user_with_role(role, username=f"role-user-{index}")
                response = self.request_permission(user, self.school, permission_name)
                self.assertEqual(response.status_code == status.HTTP_200_OK, expected)

    def test_school_admin_membership_management_is_tenant_bound(self):
        admin = self.user_with_role(SchoolMembership.Role.SCHOOL_ADMIN)
        view = SchoolMembershipListCreateView.as_view()

        request = self.factory.get("/api/v1/schools/")
        force_authenticate(request, user=admin)
        allowed = view(request, school_id=str(self.school.pk))

        request = self.factory.get("/api/v1/schools/")
        force_authenticate(request, user=admin)
        denied = view(request, school_id=str(self.other_school.pk))

        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        new_staff = self.factory.post(
            "/api/v1/schools/memberships/",
            {
                "email": "new-teacher@example.com",
                "first_name": "New",
                "last_name": "Teacher",
                "role": SchoolMembership.Role.TEACHER,
            },
            format="json",
        )
        force_authenticate(new_staff, user=admin)
        created = view(new_staff, school_id=str(self.school.pk))
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        teacher = User.objects.get(login_email="new-teacher@example.com")
        membership = teacher.school_memberships.get(school=self.school)
        self.assertEqual(membership.role, SchoolMembership.Role.TEACHER)
        self.assertFalse(teacher.has_usable_password())

    def test_manager_teacher_accountant_and_receptionist_cannot_manage_memberships(self):
        for index, role in enumerate(
            (
                SchoolMembership.Role.SCHOOL_MANAGER,
                SchoolMembership.Role.TEACHER,
                SchoolMembership.Role.ACCOUNTANT,
                SchoolMembership.Role.RECEPTIONIST,
            )
        ):
            user = self.user_with_role(role, username=f"restricted-{index}")
            request = self.factory.get("/api/v1/schools/")
            force_authenticate(request, user=user)
            response = SchoolMembershipListCreateView.as_view()(
                request, school_id=str(self.school.pk)
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_school_admin_cannot_self_promote_or_assign_another_school_admin(self):
        admin = self.user_with_role(SchoolMembership.Role.SCHOOL_ADMIN)
        membership = admin.school_memberships.get(school=self.school)
        request = self.factory.patch(
            "/api/v1/schools/memberships/",
            {"role": SchoolMembership.Role.SCHOOL_ADMIN},
            format="json",
        )
        force_authenticate(request, user=admin)
        response = SchoolMembershipDetailView.as_view()(
            request,
            school_id=str(self.school.pk),
            pk=membership.pk,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        new_user = User.objects.create_user(
            username="new-staff", email="new-staff@example.com", password=None
        )
        request = self.factory.post(
            "/api/v1/schools/memberships/",
            {
                "email": new_user.email,
                "role": SchoolMembership.Role.SCHOOL_ADMIN,
            },
            format="json",
        )
        force_authenticate(request, user=admin)
        response = SchoolMembershipListCreateView.as_view()(
            request, school_id=str(self.school.pk)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_platform_superadmin_is_separate_and_can_create_schools(self):
        superadmin = User.objects.create_superuser(
            username="platform-root",
            email="root@example.com",
            password="Strong-Test-Pass-284!",
        )
        response = self.request_permission(superadmin, self.other_school, "finance.manage")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        school_admin = self.user_with_role(SchoolMembership.Role.SCHOOL_ADMIN)
        request = self.factory.post("/api/v1/schools/", {"name": "Denied School"}, format="json")
        force_authenticate(request, user=school_admin)
        denied = SchoolCreateView.as_view()(request)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        request = self.factory.post("/api/v1/schools/", {"name": "Platform School"}, format="json")
        force_authenticate(request, user=superadmin)
        allowed = SchoolCreateView.as_view()(request)
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)

    def test_revoked_membership_stops_granting_permissions(self):
        teacher = self.user_with_role(SchoolMembership.Role.TEACHER)
        membership = teacher.school_memberships.get(school=self.school)
        membership.is_active = False
        membership.save(update_fields=["is_active"])

        response = self.request_permission(teacher, self.school, "results.enter")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolProfileApiTests(TestCase):
    def setUp(self):
        self.temp_media = TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.school = School.objects.create(
            name="Profile Academy", contact_email="office@example.edu", slug="profile-academy"
        )
        self.other_school = School.objects.create(name="Other Academy", slug="other-academy")
        self.admin = User.objects.create_user(
            username="profile-admin", email="admin@example.edu", password="test-password"
        )
        self.membership = SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.second_membership = SchoolMembership.objects.create(
            user=self.admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def request(self, method, path, data=None, school=None, **kwargs):
        return getattr(self.client, method)(
            path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), **kwargs
        )

    @staticmethod
    def png_file(name="school.png", size=(20, 20), content=None):
        if content is None:
            image = Image.new("RGB", size, "#285744")
            output = BytesIO()
            image.save(output, format="PNG")
            content = output.getvalue()
        return SimpleUploadedFile(name, content, content_type="image/png")

    def test_profile_read_update_and_school_code_is_immutable_through_profile_api(self):
        response = self.request("get", "/api/v1/schools/profile/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], "profile-academy")

        response = self.request(
            "patch", "/api/v1/schools/profile/",
            {"name": "Profile Academy Updated", "slug": "changed-code", "state": "Lagos"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Profile Academy Updated")
        self.assertEqual(self.school.slug, "profile-academy")
        self.assertEqual(self.school.state, "Lagos")

    def test_settings_are_initialized_with_defaults_and_can_be_updated(self):
        response = self.request("get", "/api/v1/schools/settings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["default_currency"], "NGN")
        self.assertEqual(response.data["time_zone"], "Africa/Lagos")
        self.assertEqual(School.objects.get(pk=self.school.pk).settings.date_format, "DD/MM/YYYY")

        response = self.request(
            "patch", "/api/v1/schools/settings/",
            {"default_currency": "usd", "date_format": "YYYY-MM-DD", "branding_primary_color": "#aabbcc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["default_currency"], "USD")
        self.assertEqual(response.data["branding_primary_color"], "#AABBCC")

    def test_invalid_profile_and_settings_values_return_field_errors(self):
        response = self.request("patch", "/api/v1/schools/profile/", {"name": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

        response = self.request(
            "patch", "/api/v1/schools/settings/", {"default_currency": "NOTACURRENCY"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("default_currency", response.data)

    def test_profile_and_settings_are_scoped_to_selected_membership(self):
        response = self.request("get", "/api/v1/schools/profile/", school=self.other_school)
        self.assertEqual(response.data["name"], "Other Academy")
        self.request("patch", "/api/v1/schools/profile/", {"motto": "First"}, format="json")
        first_motto = "First"
        self.request(
            "patch", "/api/v1/schools/profile/", {"motto": "Second"},
            school=self.other_school, format="json"
        )
        self.school.refresh_from_db()
        self.other_school.refresh_from_db()
        self.assertEqual(self.school.motto, first_motto)
        self.assertEqual(self.other_school.motto, "Second")

    def test_logo_upload_validates_image_and_size_and_serves_only_to_authorized_school(self):
        upload = self.request("post", "/api/v1/schools/profile/logo/", {"logo": self.png_file()}, format="multipart")
        self.assertEqual(upload.status_code, status.HTTP_200_OK)
        self.assertTrue(upload.data["logo_present"])

        logo = self.request("get", "/api/v1/schools/profile/logo/")
        self.assertEqual(logo.status_code, status.HTTP_200_OK)
        self.assertEqual(logo["Cache-Control"], "private, no-store")
        self.assertEqual(logo["X-Content-Type-Options"], "nosniff")
        logo.close()

        other_admin = User.objects.create_user(username="other-school-admin", password="test")
        SchoolMembership.objects.create(
            user=other_admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.client.force_authenticate(other_admin)
        denied_logo = self.request("get", "/api/v1/schools/profile/logo/")
        self.assertEqual(denied_logo.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)

        wrong_type = self.request(
            "post", "/api/v1/schools/profile/logo/",
            {"logo": SimpleUploadedFile("bad.txt", b"not an image", content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(wrong_type.status_code, status.HTTP_400_BAD_REQUEST)

        output = BytesIO()
        random_pixels = random.Random(9).randbytes(1200 * 1200 * 3)
        Image.frombytes("RGB", (1200, 1200), random_pixels).save(output, format="PNG")
        large = SimpleUploadedFile("large.png", output.getvalue(), content_type="image/png")
        self.assertGreater(large.size, 2 * 1024 * 1024)
        too_large = self.request("post", "/api/v1/schools/profile/logo/", {"logo": large}, format="multipart")
        self.assertEqual(too_large.status_code, status.HTTP_400_BAD_REQUEST)

    def test_roles_can_view_but_only_admin_can_edit_and_unrelated_tenant_is_hidden(self):
        for role in (
            SchoolMembership.Role.SCHOOL_MANAGER,
            SchoolMembership.Role.TEACHER,
            SchoolMembership.Role.ACCOUNTANT,
            SchoolMembership.Role.RECEPTIONIST,
        ):
            user = User.objects.create_user(username=f"viewer-{role}", password="test")
            SchoolMembership.objects.create(user=user, school=self.school, role=role)
            self.client.force_authenticate(user)
            self.assertEqual(self.request("get", "/api/v1/schools/profile/").status_code, status.HTTP_200_OK)
            denied = self.request("patch", "/api/v1/schools/profile/", {"motto": "no"}, format="json")
            self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        outsider = User.objects.create_user(username="outsider", password="test")
        self.client.force_authenticate(outsider)
        self.assertEqual(
            self.request("get", "/api/v1/schools/profile/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.request("get", "/api/v1/schools/profile/", school=self.other_school).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_unauthenticated_and_platform_admin_access(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/v1/schools/profile/", HTTP_X_SCHOOL_ID=str(self.school.pk)
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        root = User.objects.create_superuser(username="platform-root", email="root@platform.test", password="test")
        self.client.force_authenticate(root)
        response = self.request("get", "/api/v1/schools/profile/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.request("patch", "/api/v1/schools/profile/", {"motto": "Platform-managed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        created = self.client.post(
            "/api/v1/schools/", {"name": "New School", "slug": "new-school"}, format="json"
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        created_school = School.objects.get(pk=created.data["id"])
        self.assertEqual(created_school.settings.default_currency, "NGN")

        duplicate_code = self.client.post(
            "/api/v1/schools/",
            {"name": "Duplicate School", "slug": self.school.slug},
            format="json",
        )
        self.assertEqual(duplicate_code.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slug", duplicate_code.data)

