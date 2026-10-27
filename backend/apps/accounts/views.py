from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
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
from .emailing import send_password_setup_email
from .serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SchoolMembershipSerializer,
    UserProfileSerializer,
)

User = get_user_model()


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


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonRateThrottle,)

    def post(self, request, version=None):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
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
            send_password_setup_email(user)
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
