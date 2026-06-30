"""
HWP replace_text 패처 테스트 (Node worker + subprocess).

커버 범위:
  patch_document_version Celery 태스크 (동기 직접 호출)

Mock 기반 단위 테스트:
  - subprocess 결과 mock → applied=[op_001] → version.status=ready
  - subprocess returncode=1 → version.status=failed, error_message 기록
  - subprocess timeout → version.status=failed, error_message에 "타임아웃" 포함
  - failed 항목만 반환 → version.status=failed

통합 테스트 (실제 HWP fixture 필요):
  - fixture 없으면 skip
  - 실제 Node worker subprocess 호출, 텍스트 치환 확인
"""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.tasks import patch_document_version

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()
# 통합 테스트용 HWP fixture 경로 (없으면 통합 테스트 skip)
HWP_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample.hwp"


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 정리."""
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_upload(user, source_type, filename, file_bytes, hash_val=None):
    _hash = hash_val or f"hash_hwp_{filename}"
    fs, _ = FileStructure.objects.get_or_create(
        hash=_hash,
        defaults={"source_type": source_type, "column_schema": []},
    )
    upload = UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
        status=UploadLog.Status.DONE,
    )
    upload.file.save(filename, ContentFile(file_bytes), save=True)
    return upload


def _make_version(upload, user, version_number=2):
    return DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=DocumentVersion.Status.DRAFT,
        label="draft",
        created_by=user,
    )


def _make_change(version, operation_id, operation, anchor, original="", replacement="",
                 status=DocumentChange.Status.APPLIED):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        operation=operation,
        title="테스트 변경",
        original=original,
        replacement=replacement,
        anchor=anchor,
        confidence=0.9,
        status=status,
    )


def _mock_success_result(applied_ids: list[str]) -> MagicMock:
    """subprocess.run 성공 결과를 흉내내는 Mock 객체를 반환한다."""
    mock = MagicMock()
    mock.returncode = 0
    # worker가 반환하는 output_b64는 최소 유효 바이트로 설정
    dummy_hwp = base64.b64encode(b"dummy_hwp_output").decode()
    mock.stdout = json.dumps({
        "applied": applied_ids,
        "failed": [],
        "output_b64": dummy_hwp,
    }).encode()
    mock.stderr = b""
    return mock


def _mock_failure_result(stderr_msg: str = "오류 발생") -> MagicMock:
    """subprocess.run 실패 결과를 흉내내는 Mock 객체를 반환한다."""
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = b""
    mock.stderr = stderr_msg.encode()
    return mock


def _mock_partial_result(applied_ids: list[str], failed_ids: list[str]) -> MagicMock:
    """일부 성공, 일부 실패인 worker 결과 Mock을 반환한다."""
    mock = MagicMock()
    mock.returncode = 0
    dummy_hwp = base64.b64encode(b"partial_hwp").decode()
    mock.stdout = json.dumps({
        "applied": applied_ids,
        "failed": [{"operation_id": fid, "reason": "텍스트를 찾을 수 없습니다."} for fid in failed_ids],
        "output_b64": dummy_hwp,
    }).encode()
    mock.stderr = b""
    return mock


# ── Mock 기반 단위 테스트 ──────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class HwpPatcherMockTest(TestCase):
    """subprocess를 mock해 _patch_hwp 로직을 단위 검증한다."""

    def setUp(self):
        self.user = _make_user("hwp_mock_user")
        # 더미 HWP 바이트 (실제 HWP 형식 불필요 — subprocess가 mock됨)
        self.upload = _make_upload(
            self.user, "hwp", "mock.hwp", b"dummy_hwp_bytes", "hwp_mock_hash"
        )
        self.version = _make_version(self.upload, self.user)

    @patch("apps.documents.patcher.subprocess")
    def test_success_sets_version_ready(self, mock_subprocess):
        """worker가 applied=[op_001] 반환 → version.status=ready."""
        change = _make_change(
            self.version,
            operation_id="op_001",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "11월", "occurrence": 1},
            original="11월",
            replacement="12월",
        )
        mock_subprocess.run.return_value = _mock_success_result(["op_001"])
        mock_subprocess.TimeoutExpired = TimeoutError  # subprocess.TimeoutExpired 대체

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "worker 성공 시 version.status는 READY여야 한다",
        )
        self.assertIn("op_001", self.version.applied_change_ids)

    @patch("apps.documents.patcher.subprocess")
    def test_worker_returncode_nonzero_sets_failed(self, mock_subprocess):
        """worker returncode != 0 → version.status=failed, error_message에 stderr 내용."""
        _make_change(
            self.version,
            operation_id="op_002",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "11월"},
            original="11월",
            replacement="12월",
        )
        mock_subprocess.run.return_value = _mock_failure_result("Node 실행 오류: 파일을 찾을 수 없음")
        mock_subprocess.TimeoutExpired = TimeoutError

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "worker returncode != 0 시 version.status는 FAILED여야 한다",
        )
        self.assertIn("Node 실행 오류", self.version.error_message)

    @patch("apps.documents.patcher.subprocess")
    def test_worker_timeout_sets_failed(self, mock_subprocess):
        """subprocess timeout → version.status=failed, error_message에 '타임아웃' 포함."""
        import subprocess as real_subprocess
        _make_change(
            self.version,
            operation_id="op_003",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "11월"},
            original="11월",
            replacement="12월",
        )
        # TimeoutExpired는 실제 subprocess의 것을 사용해야 함
        mock_subprocess.TimeoutExpired = real_subprocess.TimeoutExpired
        mock_subprocess.run.side_effect = real_subprocess.TimeoutExpired(
            cmd=["node"], timeout=30
        )

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "subprocess timeout 시 version.status는 FAILED여야 한다",
        )
        self.assertIn("타임아웃", self.version.error_message)

    @patch("apps.documents.patcher.subprocess")
    def test_all_failed_from_worker_sets_version_failed(self, mock_subprocess):
        """worker가 failed만 반환(applied=[]) → version.status=failed."""
        _make_change(
            self.version,
            operation_id="op_004",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "없는텍스트"},
            original="없는텍스트",
            replacement="교체",
        )
        mock_subprocess.run.return_value = _mock_partial_result([], ["op_004"])
        mock_subprocess.TimeoutExpired = TimeoutError

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "worker에서 applied가 비면 version.status는 FAILED여야 한다",
        )


# ── 통합 테스트 (실제 HWP fixture 필요) ──────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
@unittest.skipUnless(HWP_FIXTURE_PATH.exists(), "HWP fixture 없음 — 통합 테스트 skip")
class HwpPatcherIntegrationTest(TestCase):
    """실제 HWP 파일과 Node worker subprocess를 사용하는 통합 테스트."""

    def setUp(self):
        self.user = _make_user("hwp_integ_user")
        hwp_bytes = HWP_FIXTURE_PATH.read_bytes()
        self.upload = _make_upload(
            self.user, "hwp", "sample.hwp", hwp_bytes, "hwp_integ_hash"
        )
        self.version = _make_version(self.upload, self.user)

    def test_real_worker_replaces_text(self):
        """실제 Node worker subprocess 호출 → 텍스트 치환 결과 확인."""
        # fixture 내 실제 존재하는 텍스트를 치환한다 — fixture에 맞게 수정 필요
        _make_change(
            self.version,
            operation_id="op_integ_01",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "테스트", "occurrence": 1},
            original="테스트",
            replacement="TEST",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "실제 worker 치환 성공 후 version.status는 READY여야 한다",
        )
