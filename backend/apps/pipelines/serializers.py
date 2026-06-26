from rest_framework import serializers

from .models import Pipeline, PipelineRun, PipelineStep


class PipelineRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineRun
        fields = ["id", "status", "started_at", "finished_at", "log"]


class PipelineStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStep
        fields = [
            "id",
            "pipeline",
            "step_type",
            "step_order",
            "label",
            "description",
            "config",
            "output_label",
            "created_at",
            "updated_at",
        ]
        # pipeline은 뷰에서 URL 파라미터로 주입 — 클라이언트 요청으로 변경 불가
        read_only_fields = ["id", "pipeline", "created_at", "updated_at"]


class PipelineSerializer(serializers.ModelSerializer):
    # 중첩 read-only steps — 파이프라인 단건/목록 조회 시 포함된다
    steps = PipelineStepSerializer(many=True, read_only=True)

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
            "steps",
        ]
        # owner는 뷰에서 request.user로 자동 주입 — 클라이언트 요청으로 변경 불가
        read_only_fields = ["id", "owner", "last_run_at", "created_at", "updated_at"]
