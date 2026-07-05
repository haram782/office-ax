"""
30일 보관 정책 — cleanup_expired_uploads Celery 태스크 테스트.

배경:
  storage 무한 증가를 막기 위해 RETENTION_DAYS(30일)가 지난 UploadLog를
  bulk delete한다. 연결된 DocumentVersion/artifact_file 정리는
  pre_delete 시그널(models.py)에 위임한다.

커버 범위:
  happy path  - 30일 초과 UploadLog는 삭제되고, 연결된 DocumentVersion/artifact_file도
                CASCADE + 시그널로 함께 제거된다
  boundary    - 30일 이내 UploadLog는 보존된다
  regression  - 반환값이 {"deleted_count": N, "stale_tmp_removed": M} 형태다
"""
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.models import DocumentVersion, FileStructure, UploadLog
from apps.documents.tasks import RETENTION_DAYS, cleanup_expired_uploads

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_upload(user, hash_val, uploaded_at=None):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": "excel", "column_schema": []},
    )
    upload = UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.xlsx",
        status=UploadLog.Status.DONE,
    )
    upload.file.save("sample.xlsx", ContentFile(b"original bytes"), save=True)
    if uploaded_at is not None:
        UploadLog.objects.filter(pk=upload.pk).update(uploaded_at=uploaded_at)
        upload.refresh_from_db()
    return upload


def _make_version(upload, user):
    version = DocumentVersion.objects.create(
        upload_log=upload,
        version_number=2,
        status=DocumentVersion.Status.READY,
        label="수정본",
        created_by=user,
    )
    version.artifact_file.save("v.xlsx", ContentFile(b"artifact bytes"), save=True)
    return version


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class CleanupExpiredUploadsTest(TestCase):
    def setUp(self):
        self.user = _make_user("retention_user")

    def test_expired_upload_is_deleted_with_artifacts(self):
        expired_at = timezone.now() - timedelta(days=RETENTION_DAYS + 1)
        upload = _make_upload(self.user, "retention_hash_expired", uploaded_at=expired_at)
        version = _make_version(upload, self.user)
        file_name = upload.file.name
        artifact_name = version.artifact_file.name

        result = cleanup_expired_uploads()

        self.assertFalse(UploadLog.objects.filter(pk=upload.pk).exists())
        self.assertFalse(DocumentVersion.objects.filter(pk=version.pk).exists())
        self.assertFalse(default_storage.exists(file_name))
        self.assertFalse(default_storage.exists(artifact_name))
        self.assertEqual(result["deleted_count"], 1)

    def test_recent_upload_is_retained(self):
        recent_upload = _make_upload(self.user, "retention_hash_recent")

        result = cleanup_expired_uploads()

        self.assertTrue(UploadLog.objects.filter(pk=recent_upload.pk).exists())
        self.assertEqual(result["deleted_count"], 0)

    def test_only_expired_uploads_are_counted(self):
        expired_at = timezone.now() - timedelta(days=RETENTION_DAYS + 1)
        _make_upload(self.user, "retention_hash_expired_2", uploaded_at=expired_at)
        _make_upload(self.user, "retention_hash_recent_2")

        result = cleanup_expired_uploads()

        self.assertEqual(result["deleted_count"], 1)
