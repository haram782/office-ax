from rest_framework import serializers

from .models import RagAsset


class RagAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = RagAsset
        fields = [
            "id",
            "kind",
            "group_name",
            "file",
            "file_size",
            "trained",
            "owner",
            "created_at",
        ]
        # owner/trained/file_size는 서버가 자동 지정 — 클라이언트 변경 불가
        read_only_fields = ["id", "owner", "trained", "file_size", "created_at"]

    def validate_file(self, value):
        if value is None:
            raise serializers.ValidationError("파일을 첨부해야 합니다.")
        return value
