"""
HULLOR e-commerce — Django settings.
সব সেটিংস environment variable থেকে আসে (Render dashboard এ বসাবেন)। লোকাল ডেভের জন্য .env ফাইল।
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name)
    return default if value in (None, "") else value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env("SECRET_KEY", "dev-only-insecure-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable সেট করুন।")

RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "storages",
    "accounts",
    "store",
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
            ]
        },
    }
]

# ---------------------------------------------------------------- Database
# Supabase Postgres: DATABASE_URL এ Supabase এর "Session pooler" connection string দিন (Render এর জন্য)।
DATABASE_URL = env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=int(env("DB_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
        ssl_require=env_bool("DB_SSL_REQUIRE", DATABASE_URL.startswith("postgres") and "localhost" not in DATABASE_URL),
    )
}
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    # Supabase transaction pooler (port 6543) এর সাথেও যেন কাজ করে
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- Static / media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Supabase Storage (S3 compatible) — ছবি আপলোডের জন্য। Render free তে ডিস্ক স্থায়ী না, তাই এটা সেট করা জরুরি।
if env("SUPABASE_S3_ACCESS_KEY"):
    from botocore.config import Config as _BotoConfig

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env("SUPABASE_S3_ACCESS_KEY"),
            "secret_key": env("SUPABASE_S3_SECRET_KEY"),
            "bucket_name": env("SUPABASE_S3_BUCKET", "hullor_images"),
            "endpoint_url": env("SUPABASE_S3_ENDPOINT"),
            "region_name": env("SUPABASE_S3_REGION", "ap-southeast-1"),
            "custom_domain": env("SUPABASE_S3_PUBLIC_DOMAIN"),
            "addressing_style": "path",
            "signature_version": "s3v4",
            "querystring_auth": False,
            "file_overwrite": False,
            "default_acl": None,
            # নতুন boto3 ডিফল্টভাবে checksum header পাঠায়, যা অনেক S3-compatible সার্ভিসে আপলোড ফেইল (৫০০) করায়।
            "client_config": _BotoConfig(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                retries={"max_attempts": 2},
                connect_timeout=10,
                read_timeout=30,
            ),
        },
    }

# ---------------------------------------------------------------- Security / CORS
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Env var এ ভুল (শেষে "/", ছোট-বড় হাতের অক্ষর) থাকলেও যেন কাজ করে, তাই normalize করা হয়।
_DEFAULT_CORS = [
    "https://hullor-nine.vercel.app",
    "https://hullor-admin-panel.vercel.app",
    "https://tryhullor.com",
    "https://www.tryhullor.com",
]
CORS_ALLOWED_ORIGINS = sorted({
    o.rstrip("/").lower()
    for o in _DEFAULT_CORS + env_list("CORS_ALLOWED_ORIGINS")
})
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", DEBUG)
# Vercel preview URL (যেমন hullor-nine-git-main-xxx.vercel.app) চালাতে চাইলে নিচের regex ব্যবহার হচ্ছে।
CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES") + [
    r"^https://hullor-[a-z0-9-]+\.vercel\.app$",
]

# ---------------------------------------------------------------- DRF / JWT
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "store.pagination.StandardPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"auth": "30/min", "order": "20/hour", "otp": "30/hour", "track": "60/hour"},
    "EXCEPTION_HANDLER": "store.exceptions.api_exception_handler",
}
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append("rest_framework.renderers.BrowsableAPIRenderer")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("ACCESS_TOKEN_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("REFRESH_TOKEN_DAYS", "30"))),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------- SMS / OTP (BulkSMSBD)
# API key/Sender ID কখনো কোডে বা GitHub এ রাখবেন না — শুধু Render → Environment এ সেট করুন।
BULKSMSBD_API_KEY = env("BULKSMSBD_API_KEY", "")
BULKSMSBD_SENDER_ID = env("BULKSMSBD_SENDER_ID", "")
BULKSMSBD_URL = env("BULKSMSBD_URL", "http://bulksmsbd.net/api/smsapi")
OTP_DAILY_LIMIT = int(env("OTP_DAILY_LIMIT", "300"))   # দিনে সর্বোচ্চ কয়টা OTP SMS (খরচ ঠেকাতে)
OTP_DEV_ECHO = env_bool("OTP_DEV_ECHO", DEBUG)          # API key না থাকলে শুধু লোকালে কোড রেসপন্সে দেখায়

# ---------------------------------------------------------------- Store defaults
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
