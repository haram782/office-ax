from rest_framework import serializers
from .models import DocumentChange, DocumentVersion, InboundEmail, UploadLog, IngestionWorkflow


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

    class Meta:
        model = DocumentVersion
        fields = ["id", "version_number", "status", "label", "summary", "applied_change_ids", "created_at"]
        read_only_fields = fields
