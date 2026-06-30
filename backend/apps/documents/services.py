from .models import DocumentVersion, UploadLog


def ensure_original_version(upload_log: UploadLog) -> DocumentVersion:
    """업로드 완료 시 원본(version_number=1, status=ORIGINAL) 버전을
    idempotent하게 보장한다. 이미 있으면 기존 것을 반환한다."""
    version, _ = DocumentVersion.objects.get_or_create(
        upload_log=upload_log,
        version_number=1,
        defaults={
            "status": DocumentVersion.Status.ORIGINAL,
            "label": "원본",
            "created_by": upload_log.user,
        },
    )
    return version
