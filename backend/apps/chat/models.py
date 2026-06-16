from django.contrib.auth import get_user_model
from django.db import models

from apps.documents.models import UploadLog

User = get_user_model()


class ChatSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Session {self.pk} — {self.user.username}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "사용자"
        ASSISTANT = "assistant", "어시스턴트"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField(blank=True)
    upload_log = models.ForeignKey(
        UploadLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
    )
    # LLM이 생성한 보정 파일 다운로드 경로 (예: /media/artifacts/corrected_abc123.xlsx)
    artifact_url = models.CharField(max_length=500, blank=True)
    # AI 교정 데이터 스니펫 — 인라인 프리뷰 렌더링용
    has_snippet = models.BooleanField(default=False)
    snippet_data = models.JSONField(
        default=dict,
        blank=True,
        # 예: {"type": "excel_preview", "headers": [...], "preview_rows": [[...]], "corrections": [{"cell": "D12", "original": "...", "corrected": "..."}]}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class UserActionLog(models.Model):
    """
    유저 행동 이벤트 로그 — sLLM 파인튜닝 데이터셋 축적 및 패턴 감지 고도화용.

    이벤트 흐름:
      file_upload → (Celery) → analysis_done | analysis_failed
      file_upload (중복) → duplicate_hit
    """

    class FileType(models.TextChoices):
        EXCEL       = "xlsx",        "엑셀 (.xlsx)"
        PDF_DIGITAL = "pdf_digital", "디지털 PDF"
        PDF_IMAGE   = "pdf_image",   "스캔 PDF / 이미지"
        # ── 향후 지원 예정 포맷 ──────────────────────
        IMAGE       = "image",       "이미지 (PNG/JPG)"
        DOCX        = "docx",        "Word 문서 (.docx)"
        PPTX        = "pptx",        "PowerPoint (.pptx)"
        HWP         = "hwp",         "한글 문서 (.hwp)"
        CSV         = "csv",         "CSV"
        UNKNOWN     = "unknown",     "알 수 없음"

    class ActionType(models.TextChoices):
        FILE_UPLOAD     = "file_upload",     "파일 업로드"
        DUPLICATE_HIT   = "duplicate_hit",   "중복 파일 재사용"
        ANALYSIS_DONE   = "analysis_done",   "AI 분석 완료"
        ANALYSIS_FAILED = "analysis_failed", "분석 실패"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="action_logs")
    session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_logs",
    )
    upload_log = models.ForeignKey(
        "documents.UploadLog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_logs",
    )
    # 이벤트 종류 (파인튜닝 학습 레이블 역할)
    action_type = models.CharField(
        max_length=32, choices=ActionType.choices, db_index=True
    )
    file_type   = models.CharField(
        max_length=20, choices=FileType.choices, default=FileType.UNKNOWN
    )
    # 레거시 태그 필드 유지 (예: "#수식_보정", "#OCR_추출")
    action_tag  = models.CharField(max_length=100, blank=True)
    # 파인튜닝용 구조화 컨텍스트 — 예: {"file_bytes": 45000, "correction_count": 4}
    meta        = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "action_type", "created_at"]),
        ]
