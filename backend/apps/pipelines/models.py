from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Pipeline(models.Model):
    """
    사용자 자동화 파이프라인 프로필.
    type에 따라 trigger_meta 구조가 달라진다:
      A (대화형)    — trigger_meta: {}
      B (이메일수신형) — trigger_meta: {"email": "..."}
      C (스케줄링형)  — trigger_meta: {"cron": "0 9 * * 1"}
    """

    class PipelineType(models.TextChoices):
        CONVERSATIONAL = "A", "대화형"
        EMAIL_INBOUND  = "B", "이메일수신형"
        SCHEDULED      = "C", "스케줄링형"

    name         = models.CharField(max_length=200)
    type         = models.CharField(max_length=1, choices=PipelineType.choices)
    trigger_meta = models.JSONField(default=dict, blank=True)
    is_active    = models.BooleanField(default=True)
    last_run_at  = models.DateTimeField(null=True, blank=True)
    owner        = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pipelines")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "파이프라인"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.type}] {self.name} — {self.owner}"
