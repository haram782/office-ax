"""
DocumentVersion.artifact_file / UploadLog.file storage 정리 시그널 테스트.

배경:
  artifact_file을 영구 저장하는 방식으로 복구(38f0f6f)한 이후, row 삭제만으로는
  storage에서 실제 파일이 지워지지 않아 orphan 파일이 남는다. pre_delete 시그널로
  단건 삭제, CASCADE 연쇄 삭제, bulk 쿼리셋 삭제 전부에서 storage 정리가
  보장되는지 검증한다.

커버 범위:
  happy path  - DocumentVersion.delete() → artifact_file storage에서 제거
  happy path  - UploadLog.delete() → file storage에서 제거
  happy path  - UploadLog.delete()로 인한 CASCADE → 연결된 모든 DocumentVersion의
                artifact_file도 함께 제거
  boundary    - bulk 쿼리셋 .delete() 에서도 시그널이 발생해 storage 정리됨
  boundary    - artifact_file/file이 비어있는 row 삭제는 에러 없이 진행됨
  failure     - storage I/O 실패 시에도 row 삭제 자체는 막히지 않음(인프라 실패 격리)
"""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from apps.documents.models import DocumentVersion, FileStructure, UploadLog

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_upload(user, hash_val, with_file=True):
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
    if with_file:
        upload.file.save("sample.xlsx", ContentFile(b"original bytes"), save=True)
    return upload


def _make_version(upload, user, with_artifact=True, version_number=2):
    version = DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=DocumentVersion.Status.READY,
        label="수정본",
        created_by=user,
    )
    if with_artifact:
        version.artifact_file.save("v.xlsx", ContentFile(b"artifact bytes"), save=True)
    return version


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionDeleteCleansArtifactTest(TestCase):
    def setUp(self):
        self.user = _make_user("cleanup_version_user")
        self.upload = _make_upload(self.user, "cleanup_hash_1")

    def test_deleting_version_removes_artifact_file_from_storage(self):
        version = _make_version(self.upload, self.user)
        artifact_name = version.artifact_file.name
        self.assertTrue(default_storage.exists(artifact_name))

        version.delete()

        self.assertFalse(default_storage.exists(artifact_name), "artifact_file이 storage에서 제거되어야 한다")

    def test_deleting_version_without_artifact_does_not_error(self):
        version = _make_version(self.upload, self.user, with_artifact=False)
        version.delete()
        self.assertFalse(DocumentVersion.objects.filter(pk=version.pk).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class UploadLogDeleteCleansFileTest(TestCase):
    def setUp(self):
        self.user = _make_user("cleanup_upload_user")

    def test_deleting_uploadlog_removes_file_from_storage(self):
        upload = _make_upload(self.user, "cleanup_hash_2")
        file_name = upload.file.name
        self.assertTrue(default_storage.exists(file_name))

        upload.delete()

        self.assertFalse(default_storage.exists(file_name), "file이 storage에서 제거되어야 한다")

    def test_cascade_delete_removes_child_version_artifacts(self):
        """UploadLog 삭제 → CASCADE로 DocumentVersion도 삭제 → artifact_file도 함께 제거."""
        upload = _make_upload(self.user, "cleanup_hash_3")
        version = _make_version(upload, self.user)
        artifact_name = version.artifact_file.name
        self.assertTrue(default_storage.exists(artifact_name))

        upload.delete()

        self.assertFalse(
            default_storage.exists(artifact_name),
            "UploadLog CASCADE 삭제 시 연결된 DocumentVersion의 artifact_file도 제거되어야 한다",
        )
        self.assertFalse(DocumentVersion.objects.filter(pk=version.pk).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BulkQuerysetDeleteCleansArtifactsTest(TestCase):
    """bulk 쿼리셋 .delete() 호출 시에도 시그널이 발생해 storage가 정리되는지 검증."""

    def setUp(self):
        self.user = _make_user("cleanup_bulk_user")

    def test_bulk_delete_removes_all_artifact_files(self):
        upload1 = _make_upload(self.user, "cleanup_bulk_hash_1")
        upload2 = _make_upload(self.user, "cleanup_bulk_hash_2")
        v1 = _make_version(upload1, self.user)
        v2 = _make_version(upload2, self.user)
        name1, name2 = v1.artifact_file.name, v2.artifact_file.name
        self.assertTrue(default_storage.exists(name1))
        self.assertTrue(default_storage.exists(name2))

        DocumentVersion.objects.filter(pk__in=[v1.pk, v2.pk]).delete()

        self.assertFalse(default_storage.exists(name1))
        self.assertFalse(default_storage.exists(name2))


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class StorageDeleteFailureDoesNotBlockRowDeleteTest(TestCase):
    """storage I/O 실패(인프라 경계)가 발생해도 row 삭제 자체는 진행되어야 한다."""

    def setUp(self):
        self.user = _make_user("cleanup_failure_user")
        self.upload = _make_upload(self.user, "cleanup_hash_failure")

    def test_storage_delete_exception_does_not_prevent_row_deletion(self):
        from unittest.mock import patch as mock_patch

        version = _make_version(self.upload, self.user)

        with mock_patch(
            "django.core.files.storage.FileSystemStorage.delete",
            side_effect=OSError("storage 접근 실패"),
        ):
            version.delete()

        self.assertFalse(
            DocumentVersion.objects.filter(pk=version.pk).exists(),
            "storage 삭제 실패와 무관하게 row는 삭제되어야 한다",
        )



class StaleTmpFileCleanupTest(TestCase):
    """
    업로드 임시 파일 정리 테스트.

    save_temp_file(delete=False)이 만든 tmp 파일은 베타 스택의 공유 볼륨에서
    아무도 지우지 않으므로, cleanup_expired_uploads가 2일 지난 문서 tmp 파일을
    함께 정리해야 한다 (M2 리뷰 발견 — 볼륨 무한 증식 방지).
    """

    def _make_tmp(self, tmp_dir, name, age_days):
        """지정 나이의 파일을 만든다."""
        import os
        import time

        path = tmp_dir / name
        path.write_bytes(b"x")
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
        return path

    def test_old_document_tmp_files_are_deleted(self):
        """2일 넘은 문서 확장자 tmp 파일은 삭제된다."""
        import tempfile
        from pathlib import Path

        from apps.documents.tasks import _cleanup_stale_tmp_files

        with tempfile.TemporaryDirectory() as d:
            tmp_dir = Path(d)
            old_xlsx = self._make_tmp(tmp_dir, "tmpabc123.xlsx", age_days=3)
            old_pdf = self._make_tmp(tmp_dir, "tmpdef456.pdf", age_days=5)

            removed = _cleanup_stale_tmp_files(tmp_dir)

            # TemporaryDirectory가 종료 시 전체를 지우므로 블록 안에서 검증한다
            self.assertEqual(removed, 2)
            self.assertFalse(old_xlsx.exists())
            self.assertFalse(old_pdf.exists())

    def test_recent_and_unrelated_files_are_kept(self):
        """[경계·안전] 최근 파일과 tmp 패턴이 아닌 파일은 남긴다 (호스트 /tmp 공용 사용 대비)."""
        import tempfile
        from pathlib import Path

        from apps.documents.tasks import _cleanup_stale_tmp_files

        with tempfile.TemporaryDirectory() as d:
            tmp_dir = Path(d)
            recent = self._make_tmp(tmp_dir, "tmpnew789.xlsx", age_days=0)
            not_ours = self._make_tmp(tmp_dir, "other-app.sock", age_days=10)
            no_prefix = self._make_tmp(tmp_dir, "report.xlsx", age_days=10)

            removed = _cleanup_stale_tmp_files(tmp_dir)

            # TemporaryDirectory가 종료 시 전체를 지우므로 블록 안에서 검증한다
            self.assertEqual(removed, 0)
            self.assertTrue(recent.exists())
            self.assertTrue(not_ours.exists())
            self.assertTrue(no_prefix.exists())

    def test_cleanup_task_reports_tmp_removed_count(self):
        """cleanup_expired_uploads 결과에 tmp 정리 건수가 포함된다."""
        from apps.documents.tasks import cleanup_expired_uploads

        result = cleanup_expired_uploads.run()
        self.assertIn("stale_tmp_removed", result)
