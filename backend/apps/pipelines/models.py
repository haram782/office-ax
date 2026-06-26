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


class PipelineStep(models.Model):
    """파이프라인을 구성하는 단계 하나."""

    class StepType(models.TextChoices):
        TRIGGER  = "trigger",  "트리거"
        RAG      = "rag",      "RAG"
        AIACTION = "aiaction", "AI 액션"
        OUTPUT   = "output",   "출력"

    pipeline     = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="steps")
    step_type    = models.CharField(max_length=50, choices=StepType.choices)
    step_order   = models.PositiveIntegerField()
    label        = models.CharField(max_length=100)
    description  = models.TextField(blank=True)
    config       = models.JSONField(default=dict)
    # 다음 노드에 전달하는 내용 요약 — 파이프라인 LLM 명세에서 노드 간 의존성을 표현
    output_label = models.CharField(max_length=200, blank=True, default="")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "파이프라인 스텝"
        ordering = ["step_order"]
        # 같은 파이프라인 내에서 step_order는 유일해야 한다
        unique_together = [("pipeline", "step_order")]

    def __str__(self) -> str:
        return f"[{self.step_order}] {self.label} ({self.step_type})"


class PipelineRun(models.Model):
    """파이프라인 단일 실행 기록."""

    STATUS_CHOICES = [
        ("success", "성공"),
        ("fail",    "실패"),
        ("running", "진행중"),
    ]

    pipeline    = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="runs")
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    started_at  = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    log         = models.TextField(blank=True)

    class Meta:
        verbose_name = "파이프라인 실행"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"[{self.status}] pipeline={self.pipeline_id} at {self.started_at}"
