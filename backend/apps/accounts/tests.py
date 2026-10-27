from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class AuthenticationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="amira",
            email="Amira@example.com",
            password="Strong-Test-Pass-284!",
            first_name="Amira",
        )
        self.login_url = reverse("auth-login", kwargs={"version": "v1"})
        self.csrf_url = reverse("auth-csrf", kwargs={"version": "v1"})
        self.me_url = reverse("auth-me", kwargs={"version": "v1"})

    def test_normalized_login_email_is_unique(self):
        duplicate = User(
            username="duplicate-email",
            email="AMIRA@EXAMPLE.COM",
        )
        duplicate.set_password("Strong-Test-Pass-284!")
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

    def _login(self, client=None):
        client = client or self.client
        csrf = client.get(self.csrf_url).data["csrfToken"]
        return client.post(
            self.login_url,
            {"email": "AMIRA@example.com", "password": "Strong-Test-Pass-284!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def test_successful_login_uses_email_returns_short_access_and_sets_http_only_refresh(self):
        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertTrue(response.cookies["school_refresh"]["httponly"])
        self.assertEqual(response.data["user"]["email"], "amira@example.com")

    def test_invalid_credentials_and_inactive_accounts_are_rejected(self):
        invalid = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": "Strong-Test-Pass-284!"},
            format="json",
        )
        self.assertEqual(inactive.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            self.login_url,
            {"email": self.user.email, "password": "Strong-Test-Pass-284!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_protected_profile_requires_authentication_and_returns_current_user(self):
        anonymous_response = self.client.get(self.me_url)
        self.assertEqual(anonymous_response.status_code, status.HTTP_401_UNAUTHORIZED)

        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.pk)
        self.assertEqual(response.data["email"], "amira@example.com")

    def test_refresh_rotates_and_blacklists_the_previous_token(self):
        login = self._login()
        old_refresh = self.client.cookies["school_refresh"].value
        old_jti = RefreshToken(old_refresh)["jti"]
        csrf = self.client.get(self.csrf_url).data["csrfToken"]

        response = self.client.post(
            reverse("auth-refresh", kwargs={"version": "v1"}),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=old_jti).exists()
        )
        self.assertNotEqual(self.client.cookies["school_refresh"].value, old_refresh)

    def test_logout_revokes_refresh_token(self):
        self._login()
        refresh = self.client.cookies["school_refresh"].value
        csrf = self.client.get(self.csrf_url).data["csrfToken"]
        response = self.client.post(
            reverse("auth-logout", kwargs={"version": "v1"}),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.cookies["school_refresh"]["max-age"], 0)
        self.client.cookies["school_refresh"] = refresh
        csrf = self.client.get(self.csrf_url).data["csrfToken"]
        refresh_response = self.client.post(
            reverse("auth-refresh", kwargs={"version": "v1"}),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_updates_hash_and_revokes_refresh_and_access(self):
        login = self._login()
        refresh = self.client.cookies["school_refresh"].value
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.post(
            reverse("auth-password-change", kwargs={"version": "v1"}),
            {
                "current_password": "Strong-Test-Pass-284!",
                "new_password": "Another-Strong-Pass-718!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Another-Strong-Pass-718!"))
        self.assertTrue(
            BlacklistedToken.objects.filter(token__token=refresh).exists()
        )
        self.assertEqual(self.client.get(self.me_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_is_generic_and_uses_one_time_token(self):
        reset_url = reverse("auth-password-reset", kwargs={"version": "v1"})
        known = self.client.post(reset_url, {"email": self.user.email}, format="json")
        unknown = self.client.post(reset_url, {"email": "missing@example.com"}, format="json")

        self.assertEqual(known.status_code, status.HTTP_200_OK)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        link = urlsplit(mail.outbox[0].body.splitlines()[-1])
        query = parse_qs(link.query)
        uid = query["uid"][0]
        token = query["token"][0]
        self.assertTrue(default_token_generator.check_token(self.user, token))

        response = self.client.post(
            reverse("auth-password-reset-confirm", kwargs={"version": "v1"}),
            {
                "uid": uid,
                "token": token,
                "new_password": "Reset-Strong-Pass-694!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reset-Strong-Pass-694!"))

    def test_invalid_or_expired_reset_token_does_not_change_password(self):
        response = self.client.post(
            reverse("auth-password-reset-confirm", kwargs={"version": "v1"}),
            {
                "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": "invalid-token",
                "new_password": "Reset-Strong-Pass-694!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Strong-Test-Pass-284!"))


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class MembershipAuthenticationTests(TestCase):
    def test_current_school_list_and_selection_require_membership(self):
        cache.clear()
        user = User.objects.create_user(
            username="multi", email="multi@example.com", password="Strong-Test-Pass-284!"
        )
        first = School.objects.create(name="First School")
        second = School.objects.create(name="Second School")
        SchoolMembership.objects.create(user=user, school=first, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=user, school=second, role=SchoolMembership.Role.ACCOUNTANT)
        login_client = APIClient()
        # Use the public login API to obtain a real bearer token.
        login_client.get(reverse("auth-csrf", kwargs={"version": "v1"}))
        csrf = login_client.cookies["csrftoken"].value
        login = login_client.post(
            reverse("auth-login", kwargs={"version": "v1"}),
            {"email": user.email, "password": "Strong-Test-Pass-284!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        login_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        schools = login_client.get(reverse("auth-schools", kwargs={"version": "v1"}))
        selected = login_client.post(
            reverse("auth-school-select", kwargs={"version": "v1"}),
            {"school_id": second.pk},
            format="json",
        )
        denied = login_client.post(
            reverse("auth-school-select", kwargs={"version": "v1"}),
            {"school_id": second.pk + 10000},
            format="json",
        )

        self.assertEqual(schools.status_code, status.HTTP_200_OK)
        self.assertEqual(len(schools.data), 2)
        self.assertEqual(selected.data["school_id"], second.pk)
        self.assertEqual(selected.data["role"], SchoolMembership.Role.ACCOUNTANT)
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)
