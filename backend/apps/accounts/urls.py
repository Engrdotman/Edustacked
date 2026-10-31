from django.urls import path

from .views import (
    CsrfTokenView,
    CurrentSchoolsView,
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    SelectSchoolView,
    SchoolSignupView,
    VerifyEmailView,
    ResendEmailVerificationView,
    DemoRequestView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("signup/", SchoolSignupView.as_view(), name="auth-signup"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("verify-email/resend/", ResendEmailVerificationView.as_view(), name="auth-verify-email-resend"),
    path("demo-request/", DemoRequestView.as_view(), name="demo-request"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("schools/", CurrentSchoolsView.as_view(), name="auth-schools"),
    path("schools/select/", SelectSchoolView.as_view(), name="auth-school-select"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]
