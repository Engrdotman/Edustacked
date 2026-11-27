from datetime import timedelta
import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.db import IntegrityError, transaction
from hashlib import sha256
from hmac import compare_digest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils.encoding import force_str
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.middleware.csrf import get_token

from apps.schools.models import SchoolMembership
from apps.schools.serializers import SchoolSelectionSerializer
from apps.schools.tenancy import resolve_authorized_school
from .emailing import (
    issue_email_verification,
    send_demo_request_notification,
    send_email_verification,
    send_password_setup_email,
    send_password_reset_email,
)
from .models import EmailVerificationToken, GoogleIdentity, GoogleLoginChallenge
from .serializers import (
    GoogleLoginSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SchoolMembershipSerializer,
    SchoolSignupSerializer,
    EmailVerificationSerializer,
    ResendEmailVerificationSerializer,
    DemoRequestSerializer,
    UserProfileSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class LoginRateThrottle(AnonRateThrottle):
    """Limit password login attempts per source IP independently of other endpoints."""

    scope = "login"


def _portal_access_denial(user, portal):
    if portal == "platform" and not user.is_superuser:
        return "This sign-in is for EDUstacked platform administrators. School owners and staff should use School sign in."
    if portal in {"school", "parent"} and user.is_superuser:
        return "Platform administrator accounts use the separate Platform sign in page."
    if portal == "school" and not SchoolMembership.objects.filter(
        user=user, is_active=True, school__is_active=True,
    ).exists():
        return "This account does not have an active school staff or owner login. Choose Parent or guardian sign in, or ask your school to invite you as staff."
    if portal == "parent":
        from apps.students.models import Guardian
        if not Guardian.objects.filter(
            user=user, is_active=True, student_links__is_active=True,
        ).exists():
            return "This account is not linked to a parent portal yet. Use School sign in, or ask your school to invite your guardian email."
    return ""


class GoogleAuthUnavailable(Exception):
    """Raised when the optional Google ID-token verifier is missing."""


class InvalidGoogleCredential(Exception):
    """Raised when Google cannot validate the submitted ID token."""


def _verify_google_id_token(credential):
    try:
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token
    except ImportError as exc:
        raise GoogleAuthUnavailable from exc

    try:
        return id_token.verify_oauth2_token(
            credential,
            GoogleRequest(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
            clock_skew_in_seconds=30,
        )
    except (ValueError, GoogleAuthError) as exc:
        raise InvalidGoogleCredential from exc


def _set_refresh_cookie(response, token):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(token),
        max_age=settings.AUTH_REFRESH_COOKIE_MAX_AGE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        httponly=settings.AUTH_REFRESH_COOKIE_HTTPONLY,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _revoke_user_refresh_tokens(user):
    for outstanding in OutstandingToken.objects.filter(user=user).iterator():
        try:
            RefreshToken(outstanding.token).blacklist()
        except (TokenError, ValueError, TypeError):
            continue


class CsrfTokenView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request, version=None):
        return Response({"csrfToken": get_token(request)})


class SchoolSignupView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = SchoolSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            school = serializer.save()
        except IntegrityError:
            return Response(
                {"detail": "Registration could not be completed with these details. Contact support if needed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "Your school account has been created. Please verify your email address to continue.", "school_name": school.name},
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selector = serializer.validated_data["selector"]
        secret = serializer.validated_data["token"]
        with transaction.atomic():
            token = EmailVerificationToken.objects.select_for_update().filter(selector=selector).first()
            supplied_hash = sha256(secret.encode("utf-8")).hexdigest()
            if (
                token is None
                or token.consumed_at is not None
                or token.expires_at <= timezone.now()
                or not compare_digest(token.token_hash, supplied_hash)
            ):
                return Response({"detail": "This verification link is invalid or has expired. Request a new link."}, status=status.HTTP_400_BAD_REQUEST)
            user = token.user
            user.email_verified_at = timezone.now()
            user.save(update_fields=("email_verified_at", "updated_at"))
            token.consumed_at = timezone.now()
            token.save(update_fields=("consumed_at",))
        refresh = RefreshToken.for_user(user)
        response = Response({
            "detail": "Your email has been verified. Your school workspace is ready.",
            "access": str(refresh.access_token),
            "user": UserProfileSerializer(user).data,
        })
        _set_refresh_cookie(response, refresh)
        return response


class ResendEmailVerificationView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = ResendEmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(login_email=serializer.validated_data["email"].strip().lower(), is_active=True, email_verified_at__isnull=True).first()
        if user:
            token, secret = issue_email_verification(user)
            transaction.on_commit(lambda user=user, selector=token.selector, secret=secret: send_email_verification(user, selector, secret))
        return Response({"detail": "If the account needs verification, a new link has been sent."})


class DemoRequestView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = DemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        demo_request = serializer.save()
        notification_status = send_demo_request_notification(demo_request)
        if notification_status == "sent":
            detail = (
                "Your request is saved. An email alert was sent to our team, and they will "
                "contact you using the details provided."
            )
        elif notification_status == "local_only":
            detail = (
                "Your request is saved. In local development, the team notification appears "
                "in the backend terminal, not your inbox."
            )
        else:
            detail = (
                "Your request is saved, but our team email alert could not be sent. Please "
                "email edustackedng@gmail.com so we can follow up."
            )
        return Response(
            {"detail": detail, "notification_status": notification_status},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginRateThrottle,)

    @staticmethod
    def _account_is_locked(email, now):
        if not isinstance(email, str) or not email.strip():
            return False
        return User.objects.filter(
            login_email=email.strip().lower(), locked_until__gt=now
        ).exists()

    @staticmethod
    def _record_failed_login(email, now):
        if not isinstance(email, str) or not email.strip():
            return
        with transaction.atomic():
            user = User.objects.select_for_update().filter(
                login_email=email.strip().lower(), is_active=True
            ).first()
            if user is None:
                return

            window = settings.AUTH_LOGIN_FAILURE_WINDOW_SECONDS
            if (
                user.failed_login_window_started_at is None
                or (now - user.failed_login_window_started_at).total_seconds() >= window
            ):
                user.failed_login_attempts = 0
                user.failed_login_window_started_at = now

            user.failed_login_attempts += 1
            update_fields = ["failed_login_attempts", "failed_login_window_started_at", "updated_at"]
            if user.failed_login_attempts >= settings.AUTH_LOGIN_FAILURE_LIMIT:
                user.locked_until = now + timedelta(
                    seconds=settings.AUTH_LOGIN_LOCKOUT_SECONDS
                )
                update_fields.append("locked_until")
            user.save(update_fields=update_fields)

    @staticmethod
    def _clear_failed_logins(user):
        if user.failed_login_attempts or user.failed_login_window_started_at or user.locked_until:
            user.failed_login_attempts = 0
            user.failed_login_window_started_at = None
            user.locked_until = None
            user.save(update_fields=(
                "failed_login_attempts", "failed_login_window_started_at", "locked_until", "updated_at"
            ))

    def post(self, request, version=None):
        now = timezone.now()
        email = request.data.get("email", "")
        if self._account_is_locked(email, now):
            raise ValidationError("Invalid email or password.")

        serializer = LoginSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            if getattr(serializer, "authentication_failed", False):
                self._record_failed_login(email, now)
            raise
        user = serializer.validated_data["user"]
        self._clear_failed_logins(user)
        portal = serializer.validated_data["portal"]
        denial = _portal_access_denial(user, portal)
        if denial:
            return Response({"detail": denial}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        response = Response(
            {"access": access, "user": UserProfileSerializer(user).data},
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, refresh)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login", "updated_at"])
        return response


@method_decorator(csrf_protect, name="dispatch")
class GoogleLoginChallengeView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginRateThrottle,)

    def post(self, request, version=None):
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            return Response(
                {"detail": "Google sign-in has not been configured yet. Use your email and password for now."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        now = timezone.now()
        GoogleLoginChallenge.objects.filter(expires_at__lte=now).delete()
        nonce = secrets.token_urlsafe(32)
        GoogleLoginChallenge.objects.create(
            nonce_hash=sha256(nonce.encode("utf-8")).hexdigest(),
            expires_at=now + timedelta(minutes=5),
        )
        return Response({"nonce": nonce, "expires_in": 300})


@method_decorator(csrf_protect, name="dispatch")
class GoogleLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginRateThrottle,)

    def post(self, request, version=None):
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            return Response(
                {"detail": "Google sign-in has not been configured yet. Use your email and password for now."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            claims = _verify_google_id_token(values["credential"])
        except GoogleAuthUnavailable:
            logger.error("Google sign-in dependency is missing from the backend environment.")
            return Response(
                {"detail": "Google sign-in is temporarily unavailable. Contact EDUstacked support."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InvalidGoogleCredential:
            return Response({"detail": "Google could not verify this sign-in. Choose your account and try again."}, status=status.HTTP_400_BAD_REQUEST)

        email = str(claims.get("email") or "").strip().lower()
        subject = str(claims.get("sub") or "").strip()
        token_nonce = str(claims.get("nonce") or "")
        if (
            claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
            or claims.get("email_verified") is not True
            or not email or not subject or not compare_digest(token_nonce, values["nonce"])
        ):
            return Response({"detail": "Google could not verify this sign-in. Choose your account and try again."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        nonce_hash = sha256(values["nonce"].encode("utf-8")).hexdigest()
        try:
            with transaction.atomic():
                challenge = GoogleLoginChallenge.objects.select_for_update().filter(
                    nonce_hash=nonce_hash, expires_at__gt=now, consumed_at__isnull=True,
                ).first()
                if challenge is None:
                    return Response({"detail": "This Google sign-in expired or was already used. Try again."}, status=status.HTTP_400_BAD_REQUEST)
                challenge.consumed_at = now
                challenge.save(update_fields=("consumed_at",))

                identity = GoogleIdentity.objects.select_related("user").filter(subject=subject).first()
                if identity:
                    user = User.objects.select_for_update().filter(
                        pk=identity.user_id, is_active=True, email_verified_at__isnull=False,
                    ).first()
                    if user is None:
                        return Response({"detail": "This EDUstacked account is inactive or needs email verification."}, status=status.HTTP_403_FORBIDDEN)
                else:
                    user = User.objects.select_for_update().filter(
                        login_email=email, is_active=True, email_verified_at__isnull=False,
                    ).first()
                    if user is None:
                        return Response({"detail": "No active, verified EDUstacked account matches this Google address. Ask your school to invite you or register your school first."}, status=status.HTTP_403_FORBIDDEN)

                # Check portal separation before creating or changing a Google link.
                denial = _portal_access_denial(user, values["portal"])
                if denial:
                    return Response({"detail": denial}, status=status.HTTP_403_FORBIDDEN)

                if identity:
                    identity.email = email
                    identity.last_authenticated_at = now
                    identity.save(update_fields=("email", "last_authenticated_at"))
                else:
                    if GoogleIdentity.objects.filter(user=user).exists():
                        return Response({"detail": "This EDUstacked account is already linked to another Google account. Contact support if you need to change it."}, status=status.HTTP_409_CONFLICT)
                    GoogleIdentity.objects.create(
                        user=user, subject=subject, email=email, last_authenticated_at=now,
                    )
                user.last_login = now
                user.save(update_fields=("last_login", "updated_at"))
        except IntegrityError:
            # Unique subject/user constraints protect account binding if two
            # Google callbacks for this account arrive at nearly the same time.
            return Response(
                {"detail": "This EDUstacked account is already linked to a different Google account. Contact support if you need help."},
                status=status.HTTP_409_CONFLICT,
            )

        refresh = RefreshToken.for_user(user)
        response = Response({"access": str(refresh.access_token), "user": UserProfileSerializer(user).data})
        _set_refresh_cookie(response, refresh)
        return response


@method_decorator(csrf_protect, name="dispatch")
class RefreshView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, version=None):
        refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not refresh:
            return Response(
                {"detail": "Refresh token is missing or invalid."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TokenRefreshSerializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, ValidationError, TypeError, ValueError):
            response = Response(
                {"detail": "Refresh token is missing or invalid."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _clear_refresh_cookie(response)
            return response

        data = serializer.validated_data
        rotated_refresh = data.pop("refresh", None)
        response = Response({"access": data["access"]})
        if rotated_refresh:
            _set_refresh_cookie(response, rotated_refresh)
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, version=None):
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except (TokenError, ValueError, TypeError):
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class CurrentUserView(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get(self, request, version=None):
        return Response(UserProfileSerializer(request.user).data)


class CurrentSchoolsView(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get(self, request, version=None):
        if request.user.is_superuser:
            from apps.schools.models import School

            schools = School.objects.filter(is_active=True).order_by("name")
            return Response(
                [
                    {
                        "school_id": school.pk,
                        "school_name": school.name,
                        "school_slug": school.slug,
                        "role": "platform_superadmin",
                    }
                    for school in schools
                ]
            )

        memberships = SchoolMembership.objects.select_related("school").filter(
            user=request.user,
            is_active=True,
            school__is_active=True,
        ).order_by("school__name")
        return Response(SchoolMembershipSerializer(memberships, many=True).data)


class SelectSchoolView(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def post(self, request, version=None):
        serializer = SchoolSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            school = resolve_authorized_school(
                request.user, serializer.validated_data["school_id"]
            )
        except Http404:
            return Response({"detail": "School is unavailable."}, status=status.HTTP_404_NOT_FOUND)
        membership = None
        if not request.user.is_superuser:
            membership = SchoolMembership.objects.get(
                user=request.user, school=school, is_active=True
            )
        return Response(
            {
                "school_id": school.pk,
                "school_name": school.name,
                "school_slug": school.slug,
                "role": membership.role if membership else "platform_superadmin",
                "school_verification_status": school.verification_status,
                "school_verification_reason": school.verification_reason,
                "school_accessible": school.is_active and school.verification_status != school.VerificationStatus.SUSPENDED,
            }
        )


class PasswordChangeView(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def post(self, request, version=None):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        _revoke_user_refresh_tokens(request.user)
        return Response({"detail": "Password changed. Please sign in again."})


class PasswordResetRequestView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(login_email=email, is_active=True).first()
        if user:
            send_password_reset_email(user)
        return Response(
            {"detail": "If an active account matches that email, password instructions have been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"detail": "Reset link is invalid or expired."}, status=400)

        token = serializer.validated_data["token"]
        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Reset link is invalid or expired."}, status=400)
        try:
            validate_password(serializer.validated_data["new_password"], user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=400)

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        _revoke_user_refresh_tokens(user)
        return Response({"detail": "Password has been reset. You may now sign in."})
