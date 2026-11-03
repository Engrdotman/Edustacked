import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.environ.get("LOCAL_CBT_SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("Set LOCAL_CBT_SECRET_KEY to a random value of at least 32 characters.")
DEBUG = os.environ.get("LOCAL_CBT_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("LOCAL_CBT_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "rest_framework", "offline_exam.apps.OfflineExamConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "localcbt.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "localcbt.wsgi.application"
ASGI_APPLICATION = "localcbt.asgi.application"
DATABASE_PATH = Path(os.environ.get("LOCAL_CBT_DATABASE", BASE_DIR / "data" / "local-cbt.sqlite3"))
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE_PATH, "OPTIONS": {"timeout": 30}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("LOCAL_CBT_TIME_ZONE", "Africa/Lagos")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
CBT_PACKAGE_SIGNING_KEY = os.environ.get("CBT_PACKAGE_SIGNING_KEY", "")
CBT_LICENSE_SIGNING_KEY = os.environ.get("CBT_LICENSE_SIGNING_KEY", "")
CENTRAL_SYNC_URL = os.environ.get("CENTRAL_SYNC_URL", "").rstrip("/")
CENTRAL_SYNC_TOKEN = os.environ.get("CENTRAL_SYNC_TOKEN", "")
CENTRAL_SYNC_VERIFY_TLS = os.environ.get("CENTRAL_SYNC_VERIFY_TLS", "true").lower() not in {"0", "false", "no"}
LOCAL_CBT_TOKEN_TTL_HOURS = int(os.environ.get("LOCAL_CBT_TOKEN_TTL_HOURS", "12"))
LOCAL_CBT_MAX_SYNC_RETRIES = int(os.environ.get("LOCAL_CBT_MAX_SYNC_RETRIES", "12"))
LOCAL_CBT_SYNC_BATCH_SIZE = int(os.environ.get("LOCAL_CBT_SYNC_BATCH_SIZE", "25"))
LOCAL_CBT_LOGIN_RATE = os.environ.get("LOCAL_CBT_LOGIN_RATE", "20/minute")
LOCAL_CBT_NUM_PROXIES = int(os.environ.get("LOCAL_CBT_NUM_PROXIES", "0"))
if not 1 <= LOCAL_CBT_TOKEN_TTL_HOURS <= 24:
    raise RuntimeError("LOCAL_CBT_TOKEN_TTL_HOURS must be between 1 and 24 hours.")
if LOCAL_CBT_MAX_SYNC_RETRIES < 1 or LOCAL_CBT_SYNC_BATCH_SIZE < 1:
    raise RuntimeError("Sync retry and batch settings must be positive integers.")
if not DEBUG and CENTRAL_SYNC_URL and not CENTRAL_SYNC_URL.lower().startswith("https://"):
    raise RuntimeError("Configure CENTRAL_SYNC_URL with HTTPS when LOCAL_CBT_DEBUG is false.")
if not DEBUG and not CENTRAL_SYNC_VERIFY_TLS:
    raise RuntimeError("CENTRAL_SYNC_VERIFY_TLS cannot be disabled outside local debug mode.")
if LOCAL_CBT_NUM_PROXIES < 0:
    raise RuntimeError("LOCAL_CBT_NUM_PROXIES cannot be negative.")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["offline_exam.authentication.StudentTokenAuthentication", "rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"anon": LOCAL_CBT_LOGIN_RATE},
    "NUM_PROXIES": LOCAL_CBT_NUM_PROXIES or None,
}
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
