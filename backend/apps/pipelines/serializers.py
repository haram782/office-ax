from rest_framework import serializers

from .models import Pipeline


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = [
            "id",
            "name",
            "type",
            "trigger_meta",
            "is_active",
            "last_run_at",
            "owner",
            "created_at",
            "updated_at",
        ]
        # owner는 뷰에서 request.user로 자동 주입 — 클라이언트 요청으로 변경 불가
        read_only_fields = ["id", "owner", "last_run_at", "created_at", "updated_at"]
