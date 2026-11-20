"""Django settings. All environment-specific values come from environment variables (see .env.example)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load <repo>/.env for local development; real environment variables win.
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip())


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
    SECRET_KEY = "insecure-dev-only-key"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "simple_history",
    "core",
    "accounts",
    "projects",
    "datasets",
    "research",
    "reports",
    "equipment",
    "inventory",
    "procurement",
    "knowledge",
    "meetings",
    "achievements",
    "specimens",
    "workbench",
    "system",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "lab"),
        "USER": os.environ.get("POSTGRES_USER", "lab"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "TEST": {"NAME": os.environ.get("DB_TEST_NAME") or None},
    }
}

# Shared by all Gunicorn workers (login throttle counts). The table is created by core/migrations/0001.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "django_cache"}}

# Enable only after the independent retention job is installed; see README.
LOGIN_AUDIT_ENABLED = os.environ.get("LOGIN_AUDIT_ENABLED", "0") == "1"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"

# Uploaded files are private: MEDIA_URL is intentionally NOT routed. Files are only
# served through permission-checked download views. Code must go through Django's
# storage API (FileField / default_storage) so the backend can be switched to S3-compatible
# object storage by changing STORAGES only.
MEDIA_ROOT = Path(os.environ.get("DATA_ROOT") or BASE_DIR / "var" / "data")
LAB_NAS_STORAGE_ID = os.environ.get("LAB_NAS_STORAGE_ID", "")
if LAB_NAS_STORAGE_ID:
    STORAGES = {
        "default": {"BACKEND": "core.nas_storage.NasFileStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", 2 * 1024**3))
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024**2  # larger uploads spool to a temp file
# Put the spool directory on the data disk in production; the system temp may be too small for 2GB files.
FILE_UPLOAD_TEMP_DIR = os.environ.get("FILE_UPLOAD_TEMP_DIR") or None

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Mail (SMTP account, on/off) is set in the web UI, 系统管理 → 邮件, and read per message by core/mail.py.

# The release tag of the running images (APP_VERSION in the server's .env picks them); "local" for a build from source.
APP_VERSION = os.environ.get("APP_VERSION") or "local"
# GitHub repository whose latest release 系统管理 → 版本 compares against (a fork sets its own).
UPDATE_REPO = os.environ.get("UPDATE_REPO") or "cacdcaecawae/lab-management-platform"

# History change reasons (e.g. why a record was returned) can exceed the default 100 chars.
SIMPLE_HISTORY_HISTORY_CHANGE_REASON_USE_TEXT_FIELD = True

# Session cookie auth for the SPA (same origin via Vite proxy / Nginx).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 14 * 24 * 3600
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to send X-CSRFToken
# Secure cookies need HTTPS; DJANGO_SECURE_COOKIES=0 only for an HTTP-only trial deployment.
if not DEBUG and os.environ.get("DJANGO_SECURE_COOKIES", "1") == "1":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.IsActiveMember"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.Pagination",
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    "DATE_FORMAT": "%Y-%m-%d",
    # The client address (login throttle) is the last X-Forwarded-For entry, the one Nginx appends. One proxy per
    # layer in front of Django: with another reverse proxy before Nginx this must be 2 (README, deployment).
    "NUM_PROXIES": 1,
}
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append("rest_framework.renderers.BrowsableAPIRenderer")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
