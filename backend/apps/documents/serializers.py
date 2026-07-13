from rest_framework import serializers
from .models import DocumentChange, DocumentVersion, InboundEmail, UploadLog, IngestionWorkflow


GENERIC_PATCH_FAILURE_MESSAGE = (
    "수정본을 만들지 못했습니다. 잠시 후 다시 시도하고, 계속되면 운영자에게 문의해 주세요."
)

# 내부 오류 원문과 독립된 사용자 안내 allowlist다. 알 수 없는 코드는 generic 문구로 수렴한다.
FAILURE_MESSAGE_BY_CODE = {
    "ambiguous_anchor": "수정할 위치가 여러 곳입니다. 위치 단서를 더해 다시 요청해 주세요.",
    "render_validation_failed": (
        "수정 결과 검증을 통과하지 못해 잘못된 결과물이 저장되지 않도록 생성을 중단했습니다. "
        "다시 시도하고, 계속되면 운영자에게 문의해 주세요."
    ),
    "patch_failed": GENERIC_PATCH_FAILURE_MESSAGE,
    "source_file_missing": "원본 파일을 찾지 못했습니다. 파일을 다시 업로드해 주세요.",
    "unsupported_format": "이 파일 형식은 수정본 생성을 지원하지 않습니다. 지원되는 형식으로 다시 시도해 주세요.",
    "source_file_read_error": "원본 파일을 읽지 못했습니다. 파일을 다시 업로드해 주세요.",
    "render_exception": GENERIC_PATCH_FAILURE_MESSAGE,
    "artifact_save_error": GENERIC_PATCH_FAILURE_MESSAGE,
    "unsupported_scan": "스캔된 PDF는 아직 수정할 수 없습니다. 텍스트를 선택할 수 있는 PDF로 다시 시도해 주세요.",
    "unsupported_layout_edit": "이 요청은 문서 레이아웃 변경이 필요해 아직 지원하지 않습니다.",
    "unsupported_table_edit": "이 요청은 표 구조 변경이 필요해 아직 지원하지 않습니다.",
}


def safe_failure_code(status: str, failure_code: str) -> str:
    """종결 실패 상태에서 allowlist 코드만 반환한다."""
    has_failure = status in {"failed", "needs_confirmation"} or (
        status == "ready" and bool(failure_code)
    )
    if not has_failure:
        return ""
    if failure_code in FAILURE_MESSAGE_BY_CODE:
        return failure_code
    if status == "needs_confirmation":
        return "ambiguous_anchor"
    return "patch_failed"


def safe_failure_message(status: str, failure_code: str) -> str:
    """종결 실패 상태에만 allowlist 사용자 안내를 반환한다."""
    code = safe_failure_code(status, failure_code)
    return FAILURE_MESSAGE_BY_CODE.get(code, "")


class UploadLogSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj) -> str:
        # 파일 필드가 있고 실제 디스크에 존재하는 경우만 URL 반환
        if obj.file and obj.file.storage.exists(obj.file.name):
            return obj.file.url
        return ""

    class Meta:
        model = UploadLog
        fields = [
            "id",
            "original_filename",
            "uploaded_at",
            "status",
            "ax_task_id",
            "result",
            "file_url",
            "file_hash",
        ]
        read_only_fields = fields


class InboundEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundEmail
        fields = [
            "id",
            "sender",
            "subject",
            "attachment_filename",
            "received_at",
            "status",
        ]
        read_only_fields = fields


class WorkflowActivateSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=IngestionWorkflow.NotificationChannel.choices)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_phone_number(self, value: str) -> str:
        import re
        cleaned = re.sub(r"[\s\-]", "", value)
        if cleaned and not re.fullmatch(r"0\d{9,10}", cleaned):
            raise serializers.ValidationError("올바른 국내 휴대폰 번호를 입력하세요. 예) 01012345678")
        return cleaned


class IngestionWorkflowSerializer(serializers.ModelSerializer):
    file_structure_hash = serializers.CharField(
        source="file_structure.hash", read_only=True
    )

    class Meta:
        model = IngestionWorkflow
        fields = [
            "id",
            "file_structure_hash",
            "is_suggested",
            "suggested_at",
            "is_active",
            "activated_at",
            "notification_channel",
            "phone_number",
            "inbound_email",
        ]
        read_only_fields = fields


class DocumentChangeSerializer(serializers.ModelSerializer):
    """DocumentChange 읽기 전용 직렬화."""

    failure_code = serializers.SerializerMethodField()
    failure_message = serializers.SerializerMethodField()

    def get_failure_code(self, obj) -> str:
        return safe_failure_code(obj.status, obj.failure_code)

    def get_failure_message(self, obj) -> str:
        return safe_failure_message(obj.status, obj.failure_code)

    class Meta:
        model = DocumentChange
        fields = [
            "id",
            "operation_id",
            "plan_id",
            "format",
            "operation",
            "title",
            "original",
            "replacement",
            "reason",
            "confidence",
            "anchor",
            "patch",
            "risk_level",
            "status",
            "failure_code",
            "failure_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DocumentVersionCreateSerializer(serializers.ModelSerializer):
    """DocumentVersion 생성 요청용 — label/summary/patch_plan만 입력받는다."""

    class Meta:
        model = DocumentVersion
        fields = ["label", "summary", "patch_plan"]

    def validate_patch_plan(self, value):
        # patch_plan은 반드시 리스트여야 한다
        if not isinstance(value, list):
            raise serializers.ValidationError("patch_plan은 리스트이어야 합니다.")
        return value


class DocumentVersionSummarySerializer(serializers.ModelSerializer):
    """DocumentVersion 생성/목록 응답용 요약 직렬화."""

    failure_code = serializers.SerializerMethodField()
    failure_message = serializers.SerializerMethodField()

    def get_failure_code(self, obj) -> str:
        return safe_failure_code(obj.status, obj.failure_code)

    def get_failure_message(self, obj) -> str:
        return safe_failure_message(obj.status, obj.failure_code)

    class Meta:
        model = DocumentVersion
        fields = [
            "id", "version_number", "status", "label", "summary",
            "applied_change_ids", "needs_confirmation_change_ids",
            "failure_code", "failure_message", "created_at", "updated_at",
        ]
        read_only_fields = fields
