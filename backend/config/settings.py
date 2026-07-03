import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "apps.documents",
    "apps.chat",
    "apps.pipelines",
    "apps.rag",
    "apps.accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
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

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "officeax"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# ── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ── Swagger / OpenAPI ─────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "Office-AX API",
    "DESCRIPTION": "AI 문서 분석 및 사무 자동화 파이프라인 API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # NotificationChannel ChoiceField 중복 네이밍 경고 제거
    "ENUM_NAME_OVERRIDES": {
        "NotificationChannelEnum": "apps.documents.models.IngestionWorkflow.NotificationChannel",
    },
    # APIView 기반 웹훅 뷰의 serializer 추론 실패 경고를 로그에서 숨김
    "SCHEMA_COERCE_PATH_PK_SUFFIX": True,
}

# ── Celery ───────────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "Asia/Seoul"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = 86400  # 24시간 후 결과 자동 삭제

# ax-engine 태스크는 'ax' 큐로, Django 태스크는 기본 'celery' 큐로 분리.
# 두 워커가 서로 모르는 태스크를 가로채는 것을 방지한다.
CELERY_TASK_ROUTES = {
    "tasks.*": {"queue": "ax"},
    "documents.*": {"queue": "celery"},
    "chat.*": {"queue": "celery"},
}

# ── 업로드 파일 임시 저장 경로 ───────────────────────────────────────────────
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# ── 대시보드 월 사용량 한도 ────────────────────────────────────────────────────
# MVP 단계에서는 전역 고정값. 추후 User→Plan→limit 구조로 교체될 예정이며,
# 뷰 쪽에서 조회 로직을 메서드로 분리해 두어 교체 시 이 값만 갈아끼우면 되게 한다.
MONTHLY_TOKEN_LIMIT = int(os.environ.get("MONTHLY_TOKEN_LIMIT", 2_000_000))
MONTHLY_COST_LIMIT_KRW = int(os.environ.get("MONTHLY_COST_LIMIT_KRW", 500_000))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
