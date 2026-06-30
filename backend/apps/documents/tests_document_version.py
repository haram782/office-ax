"""
DocumentVersion / DocumentChange 모델 테스트.

커버 범위:
  1. DocumentVersion 생성 시 version_number가 같은 upload_log 내에서 1부터 자동 채번
  2. 동일 upload_log에 두 번째 버전 생성 시 version_number가 2
  3. DocumentChange.status 기본값이 "pending"
  4. DocumentVersion.patch_plan JSONField 기본값이 빈 리스트
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)

User = get_user_model()


def _make_user(username="version_tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_upload_log(user):
    """테스트용 UploadLog 픽스처 생성."""
    fs, _ = FileStructure.objects.get_or_create(
        hash="version_test_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="test_file.xlsx",
    )


class DocumentVersionAutoNumberTest(TestCase):
    """version_number 자동 채번 동작 검증."""

    def setUp(self):
        self.user = _make_user()
        self.upload_log = _make_upload_log(self.user)

    def test_first_version_number_is_one(self):
        """첫 번째 DocumentVersion의 version_number는 1이어야 한다."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.version_number, 1)

    def test_second_version_number_is_two(self):
        """동일 upload_log에 두 번째 DocumentVersion 생성 시 version_number가 2이어야 한다."""
        DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        second = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(second.version_number, 2)

    def test_version_numbers_are_per_upload_log(self):
        """서로 다른 upload_log는 version_number를 독립적으로 채번해야 한다."""
        # 두 번째 upload_log 생성
        fs, _ = FileStructure.objects.get_or_create(
            hash="version_test_hash2",
            defaults={"source_type": FileStructure.SourceType.PDF, "column_schema": []},
        )
        other_log = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="other_file.pdf",
        )

        v1_log1 = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        v1_log2 = DocumentVersion.objects.create(
            upload_log=other_log,
            created_by=self.user,
        )
        # 두 upload_log 모두 첫 버전이므로 version_number는 각각 1
        self.assertEqual(v1_log1.version_number, 1)
        self.assertEqual(v1_log2.version_number, 1)


class DocumentVersionDefaultsTest(TestCase):
    """DocumentVersion 필드 기본값 검증."""

    def setUp(self):
        self.user = _make_user(username="default_tester")
        self.upload_log = _make_upload_log(self.user)

    def test_patch_plan_default_is_empty_list(self):
        """patch_plan JSONField의 기본값은 빈 리스트이어야 한다."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.patch_plan, [])

    def test_status_default_is_draft(self):
        """status 기본값은 'draft'이어야 한다 (patch-plan-schema-v0-ko.md 11절 기준)."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.status, "draft")

    def test_applied_change_ids_default_empty(self):
        """applied_change_ids 기본값은 빈 리스트여야 한다 (on-demand 방식 전환 후)."""
        version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )
        self.assertEqual(version.applied_change_ids, [])


class DocumentChangeDefaultsTest(TestCase):
    """DocumentChange 필드 기본값 검증."""

    def setUp(self):
        self.user = _make_user(username="change_tester")
        self.upload_log = _make_upload_log(self.user)
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload_log,
            created_by=self.user,
        )

    def test_status_default_is_pending(self):
        """DocumentChange.status 기본값은 'pending'이어야 한다."""
        change = DocumentChange.objects.create(
            version=self.version,
            operation_id="3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            format="excel",
            operation="replace_cell",
            original="5,000,000",
            replacement="6,500,000",
            reason="단가 인상분 반영",
            confidence=0.95,
            anchor={"type": "cell", "sheet": "정산내역", "cell": "D12"},
        )
        self.assertEqual(change.status, "pending")
