from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


def rag_asset_upload_path(instance, filename):
    """RAG 자산 파일을 owner별 디렉토리에 저장."""
    return f"rag_assets/{instance.owner_id}/{filename}"


class RagAsset(models.Model):
    """
    RAG(검색 증강 생성) 학습용 자산 파일.
    kind에 따라 어투(tone) 또는 양식(form) 데이터로 구분된다.
    업로드 직후 trained=False, Celery 태스크 완료 시 True로 갱신.
    """

    class Kind(models.TextChoices):
        TONE = "tone", "어투"
        FORM = "form", "양식"

    kind       = models.CharField(max_length=10, choices=Kind.choices)
    group_name = models.CharField(max_length=200)
    file       = models.FileField(upload_to=rag_asset_upload_path)
    # 바이트 단위 파일 크기 — 업로드 시 자동 계산
    file_size  = models.PositiveIntegerField(default=0)
    trained    = models.BooleanField(default=False)
    owner      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rag_assets")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "RAG 자산"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.kind}] {self.group_name} — {self.owner}"
