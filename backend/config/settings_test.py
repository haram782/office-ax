"""
테스트 전용 설정 — SQLite in-memory DB 사용, 외부 서비스 의존 제거.
프로덕션 settings.py를 상속하고 DB만 교체한다.
"""
import os

# settings.py가 os.environ["DJANGO_SECRET_KEY"]를 요구하므로 미리 설정
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PASSWORD", "")

# 베타 게이트 env가 실행 환경(컨테이너 등)에 설정돼 있어도 테스트는 오염되지 않아야 한다.
# allowlist·크레딧 동작 자체는 각 테스트가 patch.dict로 명시 설정해 검증한다.
os.environ.pop("BETA_ALLOWED_EMAILS", None)
os.environ.pop("BETA_MONTHLY_CREDITS", None)

from config.settings import *  # noqa: F401, F403, E402

# SQLite in-memory로 교체 — DB 서버 없이 단위 테스트 실행 가능
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# 테스트 중 Celery task 즉시 실행 (브로커 불필요)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
