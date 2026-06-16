import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("office_ax_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "detect-weekly-patterns-nightly": {
        "task": "documents.detect_weekly_patterns",
        "schedule": crontab(hour=2, minute=0),   # 매일 새벽 2시 KST
    },
}
