import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

app = Celery(
    "ax_engine",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=["tasks.analyze_document", "tasks.text_chat", "tasks.generate_patch_plan"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    result_expires=86400,
    # Django 워커와 큐 분리: AX Engine은 'ax' 큐만, Django 워커는 'celery' 큐만 처리.
    task_default_queue="ax",
    task_routes={
        "tasks.*": {"queue": "ax"},
        "documents.*": {"queue": "celery"},
    },
)
