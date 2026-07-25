"""
XLSX patcher TDD 테스트.

커버 범위:
  선행 보정 1: 파일 업로드 시 UploadLog.file에 원본 저장
  선행 보정 2: notify_analysis_complete 호출 시 original DocumentVersion 자동 생성
  선행 보정 3: 중복 호출 시 DocumentVersion 중복 생성 방지
  태스크 (4-9): patch_document_version Celery 태스크 동작
  API (10-11): POST /api/v1/uploads/{upload_id}/versions/{version_id}/patch/ 트리거
"""
import io
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.tasks import notify_analysis_complete, patch_document_version

User = get_user_model()

# 테스트 세션 동안 사용할 임시 미디어 루트
TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_patcher_test_")


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 삭제."""
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_file_structure(hash_val="xlsx_patcher_hash"):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return fs


def _make_upload(user, fs=None):
    if fs is None:
        fs = _make_file_structure()
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.xlsx",
    )


def _make_xlsx_bytes(sheet_name: str = "정산내역", data: dict | None = None) -> bytes:
    """테스트용 인메모리 XLSX 생성."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    if data:
        for cell_ref, value in data.items():
            ws[cell_ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── 선행 보정 1: 파일 업로드 시 UploadLog.file 저장 ──────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class UploadFileSaveTest(TestCase):
    """파일 업로드 시 UploadLog.file 원본 저장 테스트."""

    def setUp(self):
        self.user = _make_user("upload_file_user")
        self.client = _authed(self.user)

    @patch("apps.documents.views.current_app.send_task")
    def test_upload_saves_original_file(self, mock_send):
        """파일 업로드 시 UploadLog.file에 원본이 저장된다."""
        mock_send.return_value = MagicMock(id="test-task-id")
        content = _make_xlsx_bytes()
        uploaded = SimpleUploadedFile(
            "sample.xlsx",
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        self.assertEqual(resp.status_code, 202)

        upload_log = UploadLog.objects.get(pk=resp.data["upload_id"])
        self.assertTrue(
            bool(upload_log.file),
            "UploadLog.file에 파일이 저장되어 있어야 한다",
        )


# ── 선행 보정 2+3: notify_analysis_complete → original DocumentVersion 생성 ──


class NotifyCreateVersionTest(TestCase):
    """notify_analysis_complete 후 original DocumentVersion 생성 테스트."""

    def setUp(self):
        self.user = _make_user("notify_version_user")
        self.upload = _make_upload(self.user, _make_file_structure("notify_hash"))

    def test_notify_creates_original_version(self):
        """notify_analysis_complete 호출 시 version_number=1, status='original'인 DocumentVersion이 생성된다."""
        notify_analysis_complete(self.upload.pk, {"summary": "테스트", "errors": []})
        self.assertTrue(
            DocumentVersion.objects.filter(
                upload_log=self.upload,
                version_number=1,
                status=DocumentVersion.Status.ORIGINAL,
            ).exists(),
            "original DocumentVersion이 생성되어야 한다",
        )

    def test_notify_idempotent(self):
        """중복 호출 시 DocumentVersion이 두 개 생기지 않는다."""
        notify_analysis_complete(self.upload.pk, {"summary": "테스트", "errors": []})
        notify_analysis_complete(self.upload.pk, {"summary": "테스트", "errors": []})
        count = DocumentVersion.objects.filter(
            upload_log=self.upload,
            version_number=1,
        ).count()
        self.assertEqual(count, 1, "중복 호출 시 버전이 하나만 생성되어야 한다")


# ── XLSX patcher 태스크 (4-9) ──────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxPatcherTaskTest(TestCase):
    """patch_document_version Celery 태스크 동작 테스트."""

    def setUp(self):
        self.user = _make_user("patcher_user")
        self.upload = _make_upload(
            self.user, _make_file_structure("patcher_hash")
        )
        # XLSX 파일 생성 후 UploadLog.file에 저장
        xlsx_bytes = _make_xlsx_bytes(
            sheet_name="정산내역",
            data={"D12": "5,000,000", "E15": "3,000,000"},
        )
        self.upload.file.save("sample.xlsx", ContentFile(xlsx_bytes), save=True)

        # draft 버전 생성
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload,
            created_by=self.user,
            status=DocumentVersion.Status.DRAFT,
        )
        # D12 셀 교체 변경 (applied 상태)
        self.change1 = DocumentChange.objects.create(
            version=self.version,
            operation_id="op_replace_d12",
            format="excel",
            operation="replace_cell",
            original="5,000,000",
            replacement="6,500,000",
            reason="단가 인상",
            confidence=0.95,
            anchor={"type": "cell", "sheet": "정산내역", "cell": "D12"},
            status=DocumentChange.Status.APPLIED,
        )

    def tearDown(self):
        # 생성된 파일 정리 (TEMP_MEDIA 전체는 teardown_module에서 삭제)
        try:
            if self.upload.file:
                self.upload.file.delete(save=False)
        except Exception:
            pass

    def test_patcher_applies_replace_cell(self):
        """applied replace_cell DocumentChange가 XLSX 셀에 반영된다."""
        from apps.documents.patcher import collect_applied_changes, render_xlsx

        changes = collect_applied_changes(self.version, operations=["replace_cell"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_xlsx(original_bytes, changes)

        result_bytes = result.output_bytes
        self.assertIsInstance(result_bytes, (bytes, bytearray), "render_xlsx는 bytes를 반환해야 한다")
        wb = openpyxl.load_workbook(io.BytesIO(result_bytes), data_only=False)
        ws = wb["정산내역"]
        self.assertEqual(
            str(ws["D12"].value),
            "6,500,000",
            "패치 후 D12 셀 값이 replacement와 같아야 한다",
        )

    def test_patcher_returns_bytes(self):
        """render_xlsx가 bytes를 반환한다."""
        from apps.documents.patcher import collect_applied_changes, render_xlsx

        changes = collect_applied_changes(self.version, operations=["replace_cell"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_xlsx(original_bytes, changes)
        self.assertIsInstance(result.output_bytes, (bytes, bytearray), "render_xlsx는 bytes를 반환해야 한다")

    def test_patcher_sets_status_ready(self):
        """version.status가 'ready'가 된다."""
        patch_document_version(self.version.pk)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "ready", "패치 성공 시 status가 ready여야 한다")

    def test_patcher_mismatch_sets_change_failed(self):
        """원본 값 불일치 시 해당 change.status='failed'로 기록하고 나머지는 적용된다."""
        # E15 셀: 실제 값은 "3,000,000", original은 다른 값 → 불일치
        change2 = DocumentChange.objects.create(
            version=self.version,
            operation_id="op_replace_e15_wrong",
            format="excel",
            operation="replace_cell",
            original="WRONG_VALUE",
            replacement="4,000,000",
            reason="불일치 테스트",
            confidence=0.8,
            anchor={"type": "cell", "sheet": "정산내역", "cell": "E15"},
            status=DocumentChange.Status.APPLIED,
        )

        patch_document_version(self.version.pk)

        self.change1.refresh_from_db()
        change2.refresh_from_db()
        self.version.refresh_from_db()

        self.assertEqual(self.change1.status, "applied", "일치하는 change1은 applied 유지")
        self.assertEqual(change2.status, "failed", "불일치한 change2는 failed로 기록")
        self.assertEqual(
            self.version.status, "ready", "하나라도 성공했으므로 version은 ready"
        )

    def test_patcher_all_mismatch_sets_version_failed(self):
        """모든 항목 불일치 시 version.status='failed'가 된다."""
        self.change1.original = "WRONG_ORIGINAL"
        self.change1.save()

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status, "failed", "모든 항목 불일치 시 version은 failed여야 한다"
        )

    def test_patcher_treats_blank_original_as_matching_empty_cell(self):
        """
        [버그 수정] LLM은 추출된 텍스트만으로는 빈 셀이 ""인지 " "인지
        구분할 수 없어, 실제로 원본값을 " "로 잘못 추정하는 경우가 있다
        (같은 문서의 다른 빈 셀은 진짜 빈 문자열이었음 — 실사용 재현).
        둘 다 "비어 있음"이라는 같은 뜻이므로 이 공백 차이로 패치를
        실패시키면 안 된다.
        """
        # F14: 아무 값도 넣지 않은 진짜 빈 셀(None)
        change_blank = DocumentChange.objects.create(
            version=self.version,
            operation_id="op_replace_f14_blank",
            format="excel",
            operation="replace_cell",
            original=" ",
            replacement="haram@gmail.com",
            reason="이메일 입력",
            confidence=0.85,
            anchor={"type": "cell", "sheet": "정산내역", "cell": "F14"},
            status=DocumentChange.Status.APPLIED,
        )

        patch_document_version(self.version.pk)

        change_blank.refresh_from_db()
        self.assertEqual(
            change_blank.status, "applied",
            "빈 셀(None/\"\")과 원본값 \" \"의 공백 차이는 매칭되어야 한다",
        )

    def test_patcher_no_source_file_sets_version_failed(self):
        """upload_log.file이 없으면 version.status='failed', error_message에 사유가 기록된다."""
        self.upload.file.delete(save=True)

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status, "failed", "파일 없으면 version은 failed여야 한다"
        )
        self.assertTrue(
            len(self.version.error_message) > 0,
            "error_message에 실패 사유가 기록되어야 한다",
        )


# ── 패치 트리거 API (10-11) ────────────────────────────────────────────────────


class PatchTriggerApiTest(TestCase):
    """POST /api/v1/uploads/{upload_id}/versions/{version_id}/patch/ 테스트."""

    def setUp(self):
        self.user = _make_user("trigger_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(
            self.user, _make_file_structure("trigger_hash")
        )
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload,
            created_by=self.user,
            status=DocumentVersion.Status.DRAFT,
        )

    def test_other_user_version_returns_403(self):
        """타인 소유 version에 patch 트리거 시 403을 반환한다."""
        other = _make_user("trigger_other")
        other_upload = _make_upload(other, _make_file_structure("trigger_other_hash"))
        other_version = DocumentVersion.objects.create(
            upload_log=other_upload,
            created_by=other,
            status=DocumentVersion.Status.DRAFT,
        )
        resp = self.client.post(
            f"/api/v1/uploads/{other_upload.pk}/versions/{other_version.pk}/patch/"
        )
        self.assertEqual(resp.status_code, 403)

    @patch("apps.documents.views.patch_document_version")
    def test_non_draft_version_returns_400(self, mock_task):
        """version.status가 'draft'가 아닐 때 patch 트리거 시 400을 반환한다."""
        self.version.status = DocumentVersion.Status.READY
        self.version.save()

        resp = self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/{self.version.pk}/patch/"
        )
        self.assertEqual(resp.status_code, 400)
        mock_task.delay.assert_not_called()
