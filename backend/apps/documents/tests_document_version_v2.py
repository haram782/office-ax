"""
DocumentVersion / DocumentChange 정합화 테스트 (v2).

patch-plan-schema-v0-ko.md 10~11절 기준으로 모델이 올바르게 수정되었는지 검증한다.

커버 범위:
  1. DocumentVersion 기본 status가 "draft"이다
  2. DocumentVersion에 parent_version 필드가 존재한다
  3. DocumentVersion.applied_change_ids 기본값이 빈 리스트이다
  4. DocumentChange.patch 기본값이 빈 dict이다
  5. DocumentChange.status에 "accepted"를 넣으면 ValidationError가 발생한다
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)

User = get_user_model()


def _make_user(username="v2_tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_upload_log(user, hash_val="v2_test_hash", source_type=FileStructure.SourceType.PDF):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": source_type, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.pdf",
    )


class DocumentVersionStatusTest(TestCase):
    """DocumentVersion.status 기본값 및 choices 검증."""

    def setUp(self):
        self.user = _make_user()
        self.upload_log = _make_upload_log(self.user)

    def test_default_status_is_draft(self):
        """DocumentVersion 생성 시 기본 status는 'draft'이어야 한다."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.status, "draft")


class DocumentVersionNewFieldsTest(TestCase):
    """DocumentVersion 신규 필드 존재 및 기본값 검증."""

    def setUp(self):
        self.user = _make_user(username="v2_fields_tester")
        self.upload_log = _make_upload_log(self.user, hash_val="v2_fields_hash")

    def test_parent_version_field_exists(self):
        """parent_version 필드가 DocumentVersion에 존재해야 한다."""
        field_names = [f.name for f in DocumentVersion._meta.get_fields()]
        self.assertIn("parent_version", field_names)

    def test_parent_version_can_be_set(self):
        """parent_version에 다른 DocumentVersion을 지정하면 저장되어야 한다."""
        parent = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        child = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
            parent_version=parent,
        )
        self.assertEqual(child.parent_version_id, parent.pk)

    def test_applied_change_ids_field_exists(self):
        """applied_change_ids 필드가 DocumentVersion에 존재해야 한다."""
        field_names = [f.name for f in DocumentVersion._meta.get_fields()]
        self.assertIn("applied_change_ids", field_names)

    def test_applied_change_ids_default_is_empty_list(self):
        """applied_change_ids의 기본값은 빈 리스트이어야 한다."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.applied_change_ids, [])


class DocumentChangePatchFieldTest(TestCase):
    """DocumentChange.patch 필드 존재 및 기본값 검증."""

    def setUp(self):
        self.user = _make_user(username="v2_change_tester")
        self.upload_log = _make_upload_log(self.user, hash_val="v2_change_hash")
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )

    def _make_change(self, operation_id="op_test_001"):
        return DocumentChange.objects.create(
            version=self.version,
            operation_id=operation_id,
            format="pdf",
            operation="annotate",
            original="",
            replacement="확인 필요",
            reason="누락 항목",
            confidence=0.9,
        )

    def test_patch_field_exists(self):
        """patch 필드가 DocumentChange에 존재해야 한다."""
        field_names = [f.name for f in DocumentChange._meta.get_fields()]
        self.assertIn("patch", field_names)

    def test_patch_default_is_empty_dict(self):
        """patch의 기본값은 빈 dict이어야 한다."""
        change = self._make_change()
        self.assertEqual(change.patch, {})


class DocumentChangeStatusChoicesTest(TestCase):
    """DocumentChange.status choices에 'accepted'가 없음을 검증."""

    def setUp(self):
        self.user = _make_user(username="v2_status_tester")
        self.upload_log = _make_upload_log(self.user, hash_val="v2_status_hash")
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )

    def test_accepted_status_raises_validation_error(self):
        """status 'accepted'는 허용되지 않으므로 full_clean() 시 ValidationError가 발생해야 한다."""
        change = DocumentChange.objects.create(
            version=self.version,
            operation_id="op_test_002",
            format="xlsx",
            operation="replace_cell",
            original="100",
            replacement="200",
            reason="테스트",
            confidence=0.8,
        )
        change.status = "accepted"
        with self.assertRaises(ValidationError):
            change.full_clean()
