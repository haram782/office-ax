import hashlib
import logging

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

User = get_user_model()

logger = logging.getLogger(__name__)


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


class InboundEmail(models.Model):
    """
    인바운드 이메일 수신 이력.
    InboundEmailWebhookView가 SendGrid 웹훅을 처리할 때 자동 생성된다.
    이메일 인박스 화면에서 수신 내역을 조회하는 원천 데이터다.
    """

    class Status(models.TextChoices):
        RECEIVED   = "received",   "수신"
        PROCESSING = "processing", "처리 중"
        DONE       = "done",       "완료"
        FAILED     = "failed",     "실패"

    # 수신 이메일과 연결된 자동화 워크플로우 (비활성화되거나 삭제되어도 이력은 보존)
    workflow   = models.ForeignKey(
        "IngestionWorkflow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_emails",
    )
    # IngestionWorkflow 삭제 이후에도 소유자 식별을 위해 직접 FK 보관
    user       = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="inbound_emails"
    )
    sender     = models.EmailField(blank=True)
    subject    = models.CharField(max_length=500, blank=True)
    # 첨부파일이 여러 개일 수 있으므로 처리된 첫 번째 파일명을 대표로 저장
    attachment_filename = models.CharField(max_length=255, blank=True)
    # 연결된 UploadLog (첨부파일 처리 결과)
    upload_log = models.ForeignKey(
        "UploadLog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_email_records",
    )
    received_at = models.DateTimeField(auto_now_add=True)
    status      = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )

    class Meta:
        verbose_name = "수신 이메일"
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.sender} → {self.subject[:30]} | {self.status}"


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


class DocumentVersion(models.Model):
    """
    원본 또는 수정 결과 문서 버전.
    version_number는 같은 upload_log 내에서 1부터 자동 채번된다.

    Status 흐름:
      original → (사용자가 수정 요청) → draft → generating → ready
                                                            ↘ failed
    """

    class Status(models.TextChoices):
        # patch-plan-schema-v0-ko.md 11절 기준 status 값
        ORIGINAL   = "original",   "원본"       # 업로드 직후 원본 버전
        DRAFT      = "draft",      "초안"       # 사용자가 apply/reject 중 (수정본 미생성)
        GENERATING = "generating", "생성 중"    # patcher 실행 중
        READY      = "ready",      "완료"       # 수정본 생성 완료
        FAILED     = "failed",     "실패"       # patcher 실패
        # anchor 후보가 여러 개라 자동 반영을 멈춘 상태 — AnchorResolver.AMBIGUOUS
        # 결과만 있고 하나라도 성공(READY)한 change가 없을 때 (anchor_resolution.py 참고)
        NEEDS_CONFIRMATION = "needs_confirmation", "위치 확인 필요"

    upload_log = models.ForeignKey(
        UploadLog,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    # v1의 parent는 v0 원본 — 체인 추적용 (원본 버전은 null)
    parent_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_versions",
    )
    # 같은 upload_log 내 1-based 자동 채번 — save()에서 처리
    version_number = models.PositiveIntegerField()
    # 사용자에게 노출되는 버전 이름 (예: "날짜 형식 통일")
    label = models.CharField(max_length=100, blank=True, default="")
    # LLM이 생성한 변경 요약
    summary = models.TextField(blank=True, default="")
    # LLM이 생성한 patch plan 원본 JSON (raw 보존용)
    patch_plan = models.JSONField(default=list)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    # patcher가 실제 파일에 반영한 operation_id 목록
    applied_change_ids = models.JSONField(default=list, blank=True)
    # AnchorResolver가 AMBIGUOUS로 판정해 자동 반영을 멈춘 operation_id 목록
    # (applied_change_ids와 동일한 패턴 — 프론트가 별도 조회 없이 상태를 구분하기 위함)
    needs_confirmation_change_ids = models.JSONField(default=list, blank=True)
    # patcher 실패 시 사유 기록 (정상 완료 시 빈 문자열)
    error_message = models.TextField(blank=True, default="")
    # API에는 이 안정 코드와 allowlist 사용자 문구만 노출하고 raw error_message는 숨긴다.
    failure_code = models.CharField(max_length=50, blank=True, default="")
    # patch 완료 결과물 — GET 다운로드는 이 파일을 그대로 반환한다(재생성하지 않음)
    artifact_file = models.FileField(blank=True, null=True, upload_to="artifacts/")
    artifact_format = models.CharField(blank=True, default="", max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="document_versions",
    )

    class Meta:
        verbose_name = "문서 버전"
        unique_together = [("upload_log", "version_number")]
        ordering = ["upload_log", "version_number"]

    def save(self, *args, **kwargs):
        # 최초 저장(pk 없음)이고 외부에서 version_number를 지정하지 않은 경우에만 채번
        if not self.pk and not self.version_number:
            last = (
                DocumentVersion.objects.filter(upload_log=self.upload_log)
                .order_by("-version_number")
                .values_list("version_number", flat=True)
                .first()
            )
            self.version_number = (last or 0) + 1
            # 주의: SELECT → INSERT 사이 동시 요청 시 같은 번호를 채번할 수 있다.
            # unique_together("upload_log", "version_number")가 DB 수준에서 중복을 막으며
            # 충돌 시 IntegrityError가 발생한다. 현재 1인 메이커 규모에서는 허용 가능.
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.upload_log_id} v{self.version_number} [{self.status}]"


class DocumentChange(models.Model):
    """
    PatchOperation을 DB에 저장한 상태 객체.
    operation_id는 patch plan JSON의 operation_id와 1:1 매핑된다.

    change_id → operation_id로 rename한 이유:
      patch-plan-schema-v0-ko.md가 operation_id를 식별자로 정의하며,
      patcher/API 양쪽에서 동일한 이름을 쓰지 않으면 매핑 오류가 생긴다.
      현재 이 필드를 참조하는 외부 코드가 없으므로 rename을 선택했다.
    """

    class Status(models.TextChoices):
        # patch-plan-schema-v0-ko.md 10절 기준 — accepted 제거
        PENDING  = "pending",  "대기"
        APPLIED  = "applied",  "적용됨"
        REJECTED = "rejected", "거부"
        FAILED   = "failed",   "실패"   # patcher 실패 대비 유지
        # anchor 후보가 여러 개(AnchorResolver.AMBIGUOUS)라 자동 반영하지 않고
        # 멈춘 상태 — FAILED와 달리 "위치를 특정할 수 없어 확인이 필요함"을 의미한다
        NEEDS_CONFIRMATION = "needs_confirmation", "위치 확인 필요"

    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name="changes",
    )
    # patch plan JSON의 operation_id와 1:1 (예: "op_001", UUID v4 모두 허용)
    # default=""는 스텁 마이그레이션의 기존 빈 row 처리용 — 실운영에서는 항상 값이 채워진다
    operation_id = models.CharField(max_length=100, db_index=True, default="")
    # 어떤 PatchPlan에서 왔는지 (예: "plan_20260628_001")
    plan_id = models.CharField(max_length=100, blank=True, default="")
    format = models.CharField(max_length=20)
    operation = models.CharField(max_length=30)
    # 카드 헤더에 표시되는 변경 제목 (예: "금액 오류 수정")
    title = models.CharField(max_length=200, blank=True, default="")
    original = models.TextField()
    replacement = models.TextField()
    reason = models.TextField()
    confidence = models.FloatField()
    # 포맷별 위치 정보 (patch-plan-schema-v0-ko.md 7절 anchor 기준)
    anchor = models.JSONField(default=dict)
    # PDF text_match anchor를 PatchPlan 생성 시점에 미리 해석한 결과
    # ({"page": <1-based>, "rect": {...}}) — 미리보기 하이라이트(PdfPageCanvas)용.
    # RESOLVED가 아니었으면(모호함/못 찾음) 빈 dict로 남아 하이라이트를 그리지 않는다.
    preview_anchor = models.JSONField(default=dict, blank=True)
    # patcher 지시 필드 (예: {"method": "pymupdf_redact_overlay", "font": "auto"})
    patch = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # patch 결과 item의 안정 코드. 사용자 문구는 serializer allowlist에서 생성한다.
    failure_code = models.CharField(max_length=50, blank=True, default="")
    # low | medium | high (스키마 risk.level에 대응)
    risk_level = models.CharField(max_length=20, blank=True, default="")
    # null=True는 스텁(0005) 기존 row에 값을 채울 수 없는 제약을 우회하기 위함.
    # auto_now_add 특성상 새 row는 항상 타임스탬프가 채워진다.
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = "문서 변경 항목"
        unique_together = [("version", "operation_id")]

    def __str__(self) -> str:
        return f"{self.operation_id[:12]}… [{self.operation}] {self.status}"


class UsageEvent(models.Model):
    """AI 호출과 문서 처리 사용량을 월별로 집계하기 위한 원천 이벤트."""

    class EventType(models.TextChoices):
        DOCUMENT_ANALYSIS = "document_analysis", "문서 분석"
        CHAT_QA = "chat_qa", "채팅 Q&A"
        PATCH_PLAN_GENERATION = "patch_plan_generation", "수정 계획 생성"
        PATCH_ARTIFACT_GENERATION = "patch_artifact_generation", "수정본 생성"
        INTENT_CLASSIFICATION = "intent_classification", "의도 분류"

    class TokenSource(models.TextChoices):
        PROVIDER_REPORTED = "provider_reported", "공급자 보고"
        ESTIMATED = "estimated", "추정"
        UNAVAILABLE = "unavailable", "확인 불가"

    class Status(models.TextChoices):
        SUCCESS = "success", "성공"
        FAILED = "failed", "실패"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="usage_events"
    )
    upload_log = models.ForeignKey(
        UploadLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_events",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_events",
    )
    chat_session = models.ForeignKey(
        "chat.ChatSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_events",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    token_source = models.CharField(
        max_length=20,
        choices=TokenSource.choices,
        default=TokenSource.UNAVAILABLE,
    )
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "사용량 이벤트"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "event_type", "created_at"]),
            models.Index(fields=["user", "status", "created_at"]),
        ]

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __str__(self) -> str:
        return f"{self.user_id} | {self.event_type} | {self.status} | {self.created_at:%Y-%m-%d}"


# ── storage 파일 정리 시그널 ───────────────────────────────────────────────────
#
# 모델 delete() 오버라이드 대신 pre_delete 시그널을 쓰는 이유:
# CASCADE 연쇄 삭제(예: UploadLog 삭제 → DocumentVersion 자동 삭제)나 쿼리셋
# bulk .delete()는 인스턴스의 커스텀 delete()를 호출하지 않고 Collector를 거치는데,
# Collector는 각 인스턴스에 대해 pre_delete/post_delete 시그널은 항상 보낸다.
# 시그널 리스너가 등록되면 Django는 해당 모델에 fast-delete 최적화를 적용하지
# 않으므로 bulk delete에서도 정상적으로 발생한다.

@receiver(pre_delete, sender=UploadLog)
def _cleanup_upload_log_file(sender, instance: "UploadLog", **kwargs) -> None:
    """UploadLog row 삭제 직전 storage에서 원본 file을 제거한다."""
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except Exception as exc:
        # storage I/O 실패는 인프라 경계 실패 — row 삭제 자체를 막지 않는다
        logger.warning("UploadLog.file storage 삭제 실패 | pk=%s | %s", instance.pk, exc)


@receiver(pre_delete, sender=DocumentVersion)
def _cleanup_document_version_artifact(sender, instance: "DocumentVersion", **kwargs) -> None:
    """DocumentVersion row 삭제 직전 storage에서 artifact_file을 제거한다."""
    if not instance.artifact_file:
        return
    try:
        instance.artifact_file.delete(save=False)
    except Exception as exc:
        logger.warning("DocumentVersion.artifact_file storage 삭제 실패 | pk=%s | %s", instance.pk, exc)
