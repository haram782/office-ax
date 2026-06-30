"""
DocumentVersion 명시적 삭제 API 테스트.

DELETE /api/v1/uploads/{upload_id}/versions/{version_id}/

커버 범위:
  happy path  - draft/ready/failed 상태 버전 삭제 → 204 + row 및 artifact_file 제거
  boundary    - status=original → 400 (원본 버전은 삭제 불가)
  boundary    - status=generating → 409 (생성 중인 버전은 삭제 불가, 레이스 컨디션 방지)
  failure     - 타인 소유 → 403
  failure     - 존재하지 않는 version_id / upload_id 불일치 → 404
"""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import DocumentVersion, FileStructure, UploadLog

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_upload(user, hash_val):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": "excel", "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.xlsx",
        status=UploadLog.Status.DONE,
    )


def _make_version(upload, user, status, version_number=2, with_artifact=False):
    version = DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=status,
        label="버전",
        created_by=user,
    )
    if with_artifact:
        version.artifact_file.save("v.xlsx", ContentFile(b"artifact bytes"), save=True)
    return version


def _url(upload_id, version_id):
    return f"/api/v1/uploads/{upload_id}/versions/{version_id}/"


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionDeleteHappyPathTest(TestCase):
    def setUp(self):
        self.user = _make_user("delete_happy_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user, "delete_happy_hash")

    def test_delete_draft_version_returns_204(self):
        version = _make_version(self.upload, self.user, DocumentVersion.Status.DRAFT)
        resp = self.client.delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(DocumentVersion.objects.filter(pk=version.pk).exists())

    def test_delete_ready_version_removes_artifact_from_storage(self):
        version = _make_version(
            self.upload, self.user, DocumentVersion.Status.READY, with_artifact=True,
        )
        artifact_name = version.artifact_file.name
        self.assertTrue(default_storage.exists(artifact_name))

        resp = self.client.delete(_url(self.upload.pk, version.pk))

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(DocumentVersion.objects.filter(pk=version.pk).exists())
        self.assertFalse(default_storage.exists(artifact_name))

    def test_delete_failed_version_returns_204(self):
        version = _make_version(self.upload, self.user, DocumentVersion.Status.FAILED)
        resp = self.client.delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 204)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionDeleteBusinessRuleTest(TestCase):
    def setUp(self):
        self.user = _make_user("delete_rule_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user, "delete_rule_hash")

    def test_original_version_cannot_be_deleted(self):
        version = _make_version(
            self.upload, self.user, DocumentVersion.Status.ORIGINAL, version_number=1,
        )
        resp = self.client.delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("원본", resp.data["detail"])
        self.assertTrue(DocumentVersion.objects.filter(pk=version.pk).exists())

    def test_generating_version_cannot_be_deleted(self):
        version = _make_version(self.upload, self.user, DocumentVersion.Status.GENERATING)
        resp = self.client.delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 409)
        self.assertIn("생성 중", resp.data["detail"])
        self.assertTrue(DocumentVersion.objects.filter(pk=version.pk).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionDeleteAccessControlTest(TestCase):
    def setUp(self):
        self.user = _make_user("delete_owner_user")
        self.other = _make_user("delete_other_user")
        self.upload = _make_upload(self.user, "delete_access_hash")

    def test_other_user_gets_403(self):
        version = _make_version(self.upload, self.user, DocumentVersion.Status.DRAFT)
        resp = _authed(self.other).delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(DocumentVersion.objects.filter(pk=version.pk).exists())

    def test_nonexistent_version_returns_404(self):
        resp = _authed(self.user).delete(_url(self.upload.pk, 999999))
        self.assertEqual(resp.status_code, 404)

    def test_version_not_belonging_to_upload_returns_404(self):
        other_upload = _make_upload(self.user, "delete_access_hash2")
        version = _make_version(other_upload, self.user, DocumentVersion.Status.DRAFT)
        resp = _authed(self.user).delete(_url(self.upload.pk, version.pk))
        self.assertEqual(resp.status_code, 404)
