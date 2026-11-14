"""Django settings for the school management API."""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-only-insecure-key-change-before-deployment")
CBT_LICENSE_SIGNING_KEY = os.getenv("CBT_LICENSE_SIGNING_KEY", SECRET_KEY)
CBT_PACKAGE_SIGNING_KEY = os.getenv("CBT_PACKAGE_SIGNING_KEY", "")
CBT_OFFLINE_GRACE_DAYS = int(os.getenv("CBT_OFFLINE_GRACE_DAYS", "7"))
if not 0 <= CBT_OFFLINE_GRACE_DAYS <= 90:
    raise ImproperlyConfigured("CBT_OFFLINE_GRACE_DAYS must be between 0 and 90 days.")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
if not DEBUG and SECRET_KEY == "local-only-insecure-key-change-before-deployment":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is disabled.")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.schools.apps.SchoolsConfig",
    "apps.academics.apps.AcademicsConfig",
    "apps.students.apps.StudentsConfig",
    "apps.staff.apps.StaffConfig",
    "apps.attendance.apps.AttendanceConfig",
    "apps.results.apps.ResultsConfig",
    "apps.report_cards.apps.ReportCardsConfig",
    "apps.billing.apps.BillingConfig",
    "apps.entitlements.apps.EntitlementsConfig",
    "apps.cbt.apps.CbtConfig",
    "apps.parent_portal.apps.ParentPortalConfig",
    "apps.reports.apps.ReportsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    parsed_database_url = urlparse(DATABASE_URL)
    if parsed_database_url.scheme in {"postgres", "postgresql"}:
        query_options = parse_qs(parsed_database_url.query)
        pg_options = {key: values[-1] for key, values in query_options.items() if key in {"sslmode", "application_name"} and values}
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": unquote(parsed_database_url.path.lstrip("/")),
                "USER": unquote(parsed_database_url.username or ""),
                "PASSWORD": unquote(parsed_database_url.password or ""),
                "HOST": parsed_database_url.hostname or "127.0.0.1",
                "PORT": str(parsed_database_url.port or 5432),
                "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
                "OPTIONS": {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5")), **pg_options},
            }
        }
    elif parsed_database_url.scheme == "sqlite":
        if not DEBUG:
            raise ImproperlyConfigured("SQLite is for development only; use PostgreSQL in deployment environments.")
        database_path = unquote(parsed_database_url.path)
        if not parsed_database_url.netloc and database_path.startswith("/") and not database_path.startswith("//"):
            database_path = database_path.lstrip("/")
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": (BASE_DIR / database_path).resolve()}}
    else:
        raise ImproperlyConfigured("DATABASE_URL must use postgresql:// or sqlite://.")
else:
    DB_ENGINE = os.getenv("DB_ENGINE", "sqlite" if DEBUG else "postgresql").lower()
    if DB_ENGINE == "sqlite":
        if not DEBUG:
            raise ImproperlyConfigured("SQLite is for development only; use PostgreSQL in deployment environments.")
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": (BASE_DIR / os.getenv("DB_NAME", "db.sqlite3")).resolve(),
            }
        }
    elif DB_ENGINE == "postgresql":
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.getenv("DB_NAME", "school_management"),
                "USER": os.getenv("DB_USER", "school_management"),
                "PASSWORD": os.getenv("DB_PASSWORD", ""),
                "HOST": os.getenv("DB_HOST", "127.0.0.1"),
                "PORT": os.getenv("DB_PORT", "5432"),
                "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
                "OPTIONS": {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5"))},
            }
        }
    else:
        raise ImproperlyConfigured("DB_ENGINE must be either 'sqlite' or 'postgresql'.")

AUTH_USER_MODEL = "accounts.User"
SCHOOL_VERIFIED_REQUIRED_CAPABILITIES = frozenset(
    capability.strip()
    for capability in os.getenv("SCHOOL_VERIFIED_REQUIRED_CAPABILITIES", "integrations.manage").split(",")
    if capability.strip()
)
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_COMPRESS = True
WHITENOISE_SKIP_MIMETYPES = ("application/javascript",)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "VERSION_PARAM": "version",
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10/minute",
        "login": os.getenv("AUTH_LOGIN_RATE", "10/minute"),
        "cbt_sync": "120/minute",
    },
}

AUTH_LOGIN_FAILURE_LIMIT = int(os.getenv("AUTH_LOGIN_FAILURE_LIMIT", "5"))
AUTH_LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_FAILURE_WINDOW_SECONDS", "900"))
AUTH_LOGIN_LOCKOUT_SECONDS = int(os.getenv("AUTH_LOGIN_LOCKOUT_SECONDS", "900"))
if AUTH_LOGIN_FAILURE_LIMIT < 1 or AUTH_LOGIN_FAILURE_WINDOW_SECONDS < 1 or AUTH_LOGIN_LOCKOUT_SECONDS < 1:
    raise ImproperlyConfigured("Login rate-limit and lockout settings must be positive integers.")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "5"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
    "UPDATE_LAST_LOGIN": False,
    "SIGNING_KEY": SECRET_KEY,
}

AUTH_REFRESH_COOKIE_NAME = os.getenv("AUTH_REFRESH_COOKIE_NAME", "school_refresh")
AUTH_REFRESH_COOKIE_PATH = "/api/v1/auth/"
AUTH_REFRESH_COOKIE_DOMAIN = os.getenv("AUTH_REFRESH_COOKIE_DOMAIN") or None
AUTH_REFRESH_COOKIE_SECURE = not DEBUG
AUTH_REFRESH_COOKIE_HTTPONLY = True
AUTH_REFRESH_COOKIE_SAMESITE = os.getenv("AUTH_REFRESH_COOKIE_SAMESITE", "Lax").strip().capitalize()
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax").strip().capitalize()
AUTH_REFRESH_COOKIE_MAX_AGE = int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7")) * 24 * 60 * 60

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
SENDGRID_SANDBOX_MODE = os.getenv("SENDGRID_SANDBOX_MODE", "false").lower() in {"1", "true", "yes"}
SENDGRID_VERIFICATION_TEMPLATE_ID = os.getenv("SENDGRID_VERIFICATION_TEMPLATE_ID", "").strip()
SENDGRID_PASSWORD_SETUP_TEMPLATE_ID = os.getenv("SENDGRID_PASSWORD_SETUP_TEMPLATE_ID", "").strip()
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "apps.core.sendgrid_backend.SendgridBackend",
).strip()
# Accept the earlier documented module path and map it to our in-project backend.
if EMAIL_BACKEND == "sendgrid_backend.SendgridBackend":
    EMAIL_BACKEND = "apps.core.sendgrid_backend.SendgridBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EDUstacked <edustackedng@gmail.com>")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() in {"1", "true", "yes"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() in {"1", "true", "yes"}
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("Choose either EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
if EMAIL_BACKEND == "apps.core.sendgrid_backend.SendgridBackend" and not SENDGRID_API_KEY:
    raise ImproperlyConfigured("SENDGRID_API_KEY must be configured when using the SendGrid email backend.")
if not DEBUG and EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not EMAIL_HOST_USER:
    raise ImproperlyConfigured("EMAIL_HOST_USER must be configured in production (non-DEBUG) mode.")
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))
EMAIL_VERIFICATION_TIMEOUT = int(os.getenv("EMAIL_VERIFICATION_TIMEOUT", "86400"))
FRONTEND_BASE_URL = os.getenv(
    "FRONTEND_BASE_URL",
    "http://localhost:5173" if DEBUG else "https://edustacked.vercel.app",
).rstrip("/")
if not DEBUG and urlparse(FRONTEND_BASE_URL).hostname in {"localhost", "127.0.0.1"}:
    # A copied local .env value must not make production verification links
    # point back to a developer's computer.
    FRONTEND_BASE_URL = "https://edustacked.vercel.app"
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
FLUTTERWAVE_SECRET_KEY = os.getenv("FLUTTERWAVE_SECRET_KEY", "")
BACHS_API_KEY = os.getenv("BACHS_API_KEY", "")
BACHS_API_BASE_URL = (
    os.getenv("BACHS_API_BASE_URL", "").strip()
    or ("https://sandbox-api.bachs.io/v1" if DEBUG else "https://api.bachs.io/v1")
).rstrip("/")
BACHS_WEBHOOK_SECRET = os.getenv("BACHS_WEBHOOK_SECRET", "")
BACHS_RETURN_URL = os.getenv("BACHS_RETURN_URL", "").strip()

LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

if DEBUG:
    CORS_ALLOWED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "DJANGO_CORS_ALLOWED_ORIGINS", "http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "x-school-id",
    ]
    CSRF_TRUSTED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]
else:
    CORS_ALLOWED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "x-school-id",
    ]
    CSRF_TRUSTED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    # Keep HTTPS redirects enabled in production by default, while allowing CI
    # API tests to use Django's default HTTP test client without receiving 301s.
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "true").strip().lower() in {
        "1", "true", "yes"
    }
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = (
        os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "false").lower()
        in {"1", "true", "yes"}
    )
    SECURE_HSTS_PRELOAD = (
        os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "false").lower()
        in {"1", "true", "yes"}
    )

# The frontend and API are served through the same Vercel origin in production.
# Django still sees the browser's original Origin on unsafe proxied requests.
# Keep the known production site trusted even if Railway has a copied local
# FRONTEND_BASE_URL; the explicit environment list remains available for other clients.
frontend_parts = urlparse(FRONTEND_BASE_URL)
frontend_origin = ""
if frontend_parts.scheme in ({"http", "https"} if DEBUG else {"https"}) and frontend_parts.netloc:
    frontend_origin = f"{frontend_parts.scheme}://{frontend_parts.netloc}"
frontend_origins = {frontend_origin} if frontend_origin else set()
if not DEBUG:
    frontend_origins.add("https://edustacked.vercel.app")
for allowed_frontend_origin in frontend_origins:
    if allowed_frontend_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(allowed_frontend_origin)
    if allowed_frontend_origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(allowed_frontend_origin)
