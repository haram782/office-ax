import hashlib

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def compute_file_structure_hash(column_names: list[str]) -> str:
    """
    Excel 전체 시트의 컬럼명을 정렬·중복제거 후 MD5 fingerprint 생성.
    동일한 템플릿의 파일이면 파일명/값과 무관하게 항상 같은 해시를 반환한다.
    """
    normalized = sorted(set(col.strip() for col in column_names if col.strip()))
    raw = ",".join(normalized).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def pdf_structure_hash(filename: str) -> str:
    """PDF는 컬럼 구조가 없으므로 파일명 패턴으로 대체 fingerprint 생성."""
    import re
    # 날짜·번호 토큰 제거 후 파일명 골격만 추출 (예: "정산서_202405.pdf" → "정산서_.pdf")
    stem = re.sub(r"[\d\-_]+", "_", filename)
    return hashlib.md5(f"pdf::{stem}".encode()).hexdigest()


# ── 모델 ─────────────────────────────────────────────────────────────────────

class FileStructure(models.Model):
    """파일 유형별 고유 구조 fingerprint. 패턴 감지의 기준 키."""

    class SourceType(models.TextChoices):
        EXCEL = "excel", "Excel (.xlsx)"
        PDF   = "pdf",   "PDF"
        CSV   = "csv",   "CSV"
        DOCX  = "docx",  "Word (.docx)"
        PPTX  = "pptx",  "PowerPoint (.pptx)"
        HWP   = "hwp",   "한글 (.hwp/.hwpx)"
        IMAGE = "image", "이미지 (PNG/JPG)"

    hash = models.CharField(max_length=32, unique=True, db_index=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    # Excel이면 원본 컬럼명 목록, PDF면 빈 리스트
    column_schema = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "파일 구조"

    def __str__(self) -> str:
        return f"[{self.source_type}] {self.hash[:8]}…"


class UploadLog(models.Model):
    """파일 업로드 시계열 로그. 패턴 감지 알고리즘의 원천 데이터."""

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        PROCESSING = "processing", "처리 중"
        DONE = "done", "완료"
        FAILED = "failed", "실패"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="upload_logs"
    )
    file_structure = models.ForeignKey(
        FileStructure,
        on_delete=models.SET_NULL,
        null=True,
        related_name="upload_logs",
    )
    original_filename = models.CharField(max_length=255)
    # 원본 파일 저장 (미리보기용, media/uploads/ 에 보관)
    file = models.FileField(upload_to="uploads/", null=True, blank=True)
    # SHA-256 해시 — 동일 파일 재업로드 시 중복 분석 방지
    file_hash = models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    ax_task_id = models.CharField(max_length=255, blank=True)
    result = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "업로드 로그"
        ordering = ["-uploaded_at"]
        indexes = [
            # 패턴 감지 쿼리에서 (user + 날짜) 기준으로 집계하므로 복합 인덱스 우선
            models.Index(fields=["user", "file_structure", "uploaded_at"]),
            models.Index(fields=["user", "uploaded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} | {self.original_filename} | {self.status}"


class IngestionWorkflow(models.Model):
    """
    자동화 파이프라인 프로필.
    - is_suggested: 패턴 감지기가 제안 플래그 설정 → 프론트에 팝업 노출
    - is_active: 유저가 팝업에서 활성화 확인 → 인바운드 이메일 발급
    """

    class NotificationChannel(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        SLACK = "slack", "Slack"
        KAKAO = "kakao", "카카오 알림톡"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="workflows"
    )
    file_structure = models.ForeignKey(
        FileStructure, on_delete=models.CASCADE, related_name="workflows"
    )
    is_suggested = models.BooleanField(default=False)
    suggested_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    notification_channel = models.CharField(
        max_length=20, choices=NotificationChannel.choices, blank=True
    )
    # 알림톡 수신용 국내 휴대폰 번호 (예: 01012345678)
    phone_number = models.CharField(max_length=20, blank=True)
    # 활성화 시 발급되는 유저 고유 수신 이메일 (SendGrid/SES 연동 키)
    inbound_email = models.EmailField(unique=True, null=True, blank=True)

    class Meta:
        verbose_name = "자동화 워크플로우"
        unique_together = [("user", "file_structure")]

    def activate(self, channel: str, phone_number: str = "") -> None:
        """유저가 자동화를 확정하면 호출. 인바운드 이메일을 발급한다."""
        self.is_active = True
        self.activated_at = timezone.now()
        self.notification_channel = channel
        self.phone_number = phone_number
        self.inbound_email = self._generate_inbound_email()
        self.save(update_fields=[
            "is_active", "activated_at", "notification_channel",
            "phone_number", "inbound_email",
        ])

    def _generate_inbound_email(self) -> str:
        # user-{userId}-{hash 앞 6자리}@officeax.com
        return f"user-{self.user_id}-{self.file_structure.hash[:6]}@officeax.com"

    def __str__(self) -> str:
        state = "활성" if self.is_active else ("제안됨" if self.is_suggested else "비활성")
        return f"{self.user} | {self.file_structure.hash[:8]} | {state}"
