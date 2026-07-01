"""
XLSX 기준 사용자 루프 전체 E2E 통합 테스트.

검증하는 전체 흐름:
  1. POST /api/v1/uploads/              → 202, upload_id
  2. notify_analysis_complete() 직접 호출 → UploadLog.status=DONE + original version 생성
  3. POST .../generate-patch-plan/      → 201, version_id + pending changes 반환
  4. PATCH /api/v1/changes/{id}/        → change 명시적 반려
  5. POST .../changes/accept-all/       → 나머지 pending → applied
  6. POST .../versions/{id}/patch/      → 202 (CELERY_TASK_ALWAYS_EAGER=True이므로 동기 실행)
  7. GET  .../versions/                 → version.status = "ready" 확인(polling 시뮬레이션)
  8. GET  .../versions/{id}/file/       → artifact 다운로드, openpyxl로 셀 값 검증

5개 테스트:
  happy path  — 1~8 전 단계 통과, 승인 change만 XLSX에 반영
  boundary    — operations 빈 배열 → 200 + version_id=null, 체인 자연 종료
  failure     — original 불일치 change는 status=failed, 나머지는 정상, version=ready
  regression  — 동일 upload에 두 번째 버전 생성 시 version_number 자동 증가,
                첫 번째 버전 artifact_file 영향 없음
  sales scenario — set_cell_style + set_number_format + set_formula가 한 매출표에서
                함께 적용되고, 의도적으로 잘못된 operation 1건은 개별 실패로 격리된다
                (document-editing-ax-next-roadmap-v1-ko.md 6.Phase5절 기준)
"""
import io
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import DocumentChange, DocumentVersion, FileStructure, UploadLog
from apps.documents.tasks import notify_analysis_complete

User = get_user_model()

# 테스트 세션 전용 임시 storage 루트 — 모듈 종료 시 일괄 삭제
TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_e2e_test_")


def teardown_module(_module):
    """모듈 종료 시 임시 storage 디렉터리 일괄 삭제."""
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 공용 픽스처 헬퍼 ──────────────────────────────────────────────────────────

def _make_user(username: str):
    return User.objects.create_user(username=username, password="pw")


def _authed(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_xlsx_bytes(sheet_name: str = "정산내역", data: dict | None = None) -> bytes:
    """
    인메모리 XLSX 생성.
    data = {"A2": "값1", "B2": "값2", ...} 형태로 셀 초기값을 지정한다.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    if data:
        for cell_ref, value in data.items():
            ws[cell_ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _patch_plan(operations: list) -> dict:
    """테스트용 mock _generate_patch_plan 반환값을 구성한다."""
    return {
        "schema": "office_ax.patch_plan.v0",
        "plan_id": "plan_e2e_test",
        "summary": "E2E 테스트용 패치 플랜",
        "operations": operations,
    }


def _xlsx_cell_value(file_bytes: bytes, sheet: str, cell_ref: str) -> str:
    """다운로드된 bytes에서 특정 시트 셀 값을 읽어 str로 반환한다."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws = wb[sheet]
    v = ws[cell_ref].value
    return str(v) if v is not None else ""


# ── happy path ────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxE2EHappyPathTest(TestCase):
    """
    1~8 전 단계를 순서대로 거쳐 최종 artifact를 검증한다.

    XLSX 레이아웃 (sheet="정산내역"):
      A2 = "20260101"  ← op1이 "2026-01-01"로 교체 예정, accept-all로 applied
      B2 = "20260201"  ← op2가 교체 예정이지만 PATCH로 명시적 반려
    """

    # mock _generate_patch_plan 반환값 — A2/B2 교체 플랜
    _MOCK_PLAN = _patch_plan([
        {
            "operation_id": "op_e2e_001",
            "format": "excel",
            "operation": "replace_cell",
            "title": "A2 날짜 형식 교정",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "YYYY-MM-DD 형식 통일",
            "confidence": 0.95,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-01-01"},
            "risk": {"level": "low"},
        },
        {
            "operation_id": "op_e2e_002",
            "format": "excel",
            "operation": "replace_cell",
            "title": "B2 날짜 형식 교정",
            "original": "20260201",
            "replacement": "2026-02-01",
            "reason": "YYYY-MM-DD 형식 통일",
            "confidence": 0.90,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "B2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-02-01"},
            "risk": {"level": "low"},
        },
    ])

    def setUp(self):
        self.user = _make_user("e2e_happy_user")
        self.client = _authed(self.user)

    @patch("apps.documents.services.patch_plan._generate_patch_plan")
    @patch("apps.documents.views.current_app.send_task")
    def test_full_xlsx_loop(self, mock_send_task, mock_gen_plan):
        """1~8 단계를 전부 거쳐 최종 XLSX에서 승인된 change만 반영됨을 검증한다."""
        mock_send_task.return_value = MagicMock(id="fake-ax-task-id")
        mock_gen_plan.return_value = self._MOCK_PLAN

        # ── 1. 파일 업로드 ──────────────────────────────────────────────────
        xlsx_bytes = _make_xlsx_bytes(
            sheet_name="정산내역",
            data={"A2": "20260101", "B2": "20260201"},
        )
        uploaded = SimpleUploadedFile(
            "sample.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        self.assertEqual(resp.status_code, 202, "업로드 응답 202 기대")

        upload_id = resp.data["upload_id"]
        upload_log = UploadLog.objects.get(pk=upload_id)
        # storage에 원본 파일이 저장됐는지 확인
        self.assertTrue(bool(upload_log.file), "UploadLog.file에 원본이 저장되어야 한다")

        # ── 2. AX 분석 완료 시뮬레이션 ──────────────────────────────────────
        analysis_result = {
            "source_type": "excel",
            "summary": "날짜 형식 오류 2건 감지",
            "errors": ["A2 날짜 형식 오류", "B2 날짜 형식 오류"],
        }
        notify_analysis_complete(upload_id, analysis_result)

        upload_log.refresh_from_db()
        self.assertEqual(upload_log.status, UploadLog.Status.DONE, "분석 완료 후 status=DONE이어야 한다")

        # original DocumentVersion(version_number=1) 자동 생성 확인
        original_version = DocumentVersion.objects.get(
            upload_log=upload_log, version_number=1,
        )
        self.assertEqual(original_version.status, DocumentVersion.Status.ORIGINAL)

        # ── 3. patch plan 생성 ──────────────────────────────────────────────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
            {"prompt": "날짜 형식을 YYYY-MM-DD로 통일해 주세요"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, "patch plan 생성 응답 201 기대")

        version_id = resp.data["version_id"]
        changes = resp.data["changes"]
        self.assertIsNotNone(version_id, "version_id가 반환되어야 한다")
        self.assertEqual(len(changes), 2, "2개 change가 생성되어야 한다")

        # draft 버전 생성 확인
        draft_version = DocumentVersion.objects.get(pk=version_id)
        self.assertEqual(draft_version.status, DocumentVersion.Status.DRAFT)
        self.assertEqual(
            DocumentChange.objects.filter(version=draft_version, status=DocumentChange.Status.PENDING).count(),
            2,
        )

        # op_e2e_002 change_id 추출 (B2 교체 — 반려 예정)
        change_to_reject = next(c for c in changes if c["operation_id"] == "op_e2e_002")

        # ── 4. change 명시적 반려 ─────────────────────────────────────────
        resp = self.client.patch(
            f"/api/v1/changes/{change_to_reject['id']}/",
            {"status": "rejected"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, "change 반려 응답 200 기대")
        self.assertEqual(
            DocumentChange.objects.get(pk=change_to_reject["id"]).status,
            DocumentChange.Status.REJECTED,
        )

        # ── 5. 나머지 pending → accept-all ──────────────────────────────────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/",
        )
        self.assertEqual(resp.status_code, 200, "accept-all 응답 200 기대")

        # op_e2e_001만 applied, op_e2e_002는 이미 rejected라 accept-all 대상 아님
        self.assertEqual(len(resp.data["applied"]), 1, "pending 1건만 applied 처리")
        self.assertEqual(len(resp.data["rejected"]), 0)

        change_accepted_id = next(
            c["id"] for c in changes if c["operation_id"] == "op_e2e_001"
        )
        self.assertEqual(
            DocumentChange.objects.get(pk=change_accepted_id).status,
            DocumentChange.Status.APPLIED,
        )

        # ── 6. patch 트리거 (CELERY_TASK_ALWAYS_EAGER=True → 동기 실행) ─────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/patch/",
        )
        self.assertEqual(resp.status_code, 202, "patch 트리거 응답 202 기대")

        # ── 7. 버전 목록으로 status 확인 (polling 시뮬레이션) ──────────────
        resp = self.client.get(f"/api/v1/uploads/{upload_id}/versions/")
        self.assertEqual(resp.status_code, 200)
        versions = resp.data
        patched = next(v for v in versions if v["id"] == version_id)
        self.assertEqual(patched["status"], "ready", "패치 완료 후 버전 status가 ready여야 한다")

        # ── 8. artifact 다운로드 및 셀 값 검증 ──────────────────────────────
        resp = self.client.get(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/file/",
        )
        self.assertEqual(resp.status_code, 200, "파일 다운로드 응답 200 기대")
        self.assertIn("attachment", resp.get("Content-Disposition", ""))

        file_bytes = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
        a2_val = _xlsx_cell_value(file_bytes, "정산내역", "A2")
        b2_val = _xlsx_cell_value(file_bytes, "정산내역", "B2")

        self.assertEqual(a2_val, "2026-01-01", "승인된 A2 change가 반영되어야 한다")
        self.assertEqual(b2_val, "20260201", "반려된 B2 change는 원본 값이 유지되어야 한다")


# ── boundary: 빈 operations ──────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxE2EEmptyOperationsTest(TestCase):
    """
    generate-patch-plan이 빈 operations를 반환할 때 체인이 자연스럽게 종료된다.

    기대 동작:
      - 200 + {"version_id": null, "changes": []} 반환
      - draft DocumentVersion이 생성되지 않음
      - 이후 patch 트리거 단계까지 진행 불필요
    """

    _EMPTY_PLAN = _patch_plan([])

    def setUp(self):
        self.user = _make_user("e2e_empty_user")
        self.client = _authed(self.user)

    @patch("apps.documents.services.patch_plan._generate_patch_plan")
    @patch("apps.documents.views.current_app.send_task")
    def test_empty_operations_ends_chain_naturally(self, mock_send_task, mock_gen_plan):
        """빈 operations일 때 200 + version_id=null을 반환하고 draft 버전이 생성되지 않는다."""
        mock_send_task.return_value = MagicMock(id="fake-task-empty")
        mock_gen_plan.return_value = self._EMPTY_PLAN

        # 업로드
        xlsx_bytes = _make_xlsx_bytes(data={"A1": "헤더"})
        uploaded = SimpleUploadedFile(
            "empty_plan.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        upload_id = resp.data["upload_id"]

        # 분석 완료 시뮬레이션
        notify_analysis_complete(upload_id, {"source_type": "excel", "summary": "이상 없음", "errors": []})

        # patch plan 요청 — 빈 operations 반환
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
            {"prompt": "문제가 없는 경우"},
            format="json",
        )

        self.assertEqual(resp.status_code, 200, "빈 operations일 때 200 기대")
        self.assertIsNone(resp.data["version_id"], "version_id가 null이어야 한다")
        self.assertEqual(resp.data["changes"], [], "changes가 빈 배열이어야 한다")

        # draft 버전이 생성되지 않았는지 확인 (original v1만 존재)
        draft_count = DocumentVersion.objects.filter(
            upload_log_id=upload_id,
            status=DocumentVersion.Status.DRAFT,
        ).count()
        self.assertEqual(draft_count, 0, "빈 operations일 때 draft 버전은 생성되지 않아야 한다")


# ── failure: original 불일치 change ─────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxE2EOriginalMismatchTest(TestCase):
    """
    change 중 하나의 original이 실제 셀 값과 불일치할 때:
      - 해당 change.status = failed
      - 나머지 change는 정상 applied
      - version.status = ready (적용 성공 항목이 1건 이상이므로)
      - 다운로드 XLSX에는 성공 change만 반영됨

    XLSX 레이아웃 (sheet="정산내역"):
      A2 = "20260101"  ← op1 original 일치 → applied 성공
      C3 = "실제값"   ← op2 original은 "WRONG" (의도적 불일치) → change.status=failed
    """

    _MISMATCH_PLAN = _patch_plan([
        {
            "operation_id": "op_mismatch_001",
            "format": "excel",
            "operation": "replace_cell",
            "title": "A2 정상 교체",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "날짜 형식 교정",
            "confidence": 0.95,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value"},
            "risk": {"level": "low"},
        },
        {
            "operation_id": "op_mismatch_002",
            "format": "excel",
            "operation": "replace_cell",
            "title": "C3 불일치 교체",
            "original": "WRONG",  # 실제 셀 값은 "실제값" — 의도적 불일치
            "replacement": "새값",
            "reason": "불일치 테스트",
            "confidence": 0.80,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "C3"},
            "patch": {"method": "openpyxl_set_value"},
            "risk": {"level": "low"},
        },
    ])

    def setUp(self):
        self.user = _make_user("e2e_mismatch_user")
        self.client = _authed(self.user)

    @patch("apps.documents.services.patch_plan._generate_patch_plan")
    @patch("apps.documents.views.current_app.send_task")
    def test_mismatch_change_fails_rest_succeeds(self, mock_send_task, mock_gen_plan):
        """original 불일치 change는 failed, 나머지는 applied, version은 ready."""
        mock_send_task.return_value = MagicMock(id="fake-task-mismatch")
        mock_gen_plan.return_value = self._MISMATCH_PLAN

        # 업로드 (C3에 실제 값 세팅)
        xlsx_bytes = _make_xlsx_bytes(
            sheet_name="정산내역",
            data={"A2": "20260101", "C3": "실제값"},
        )
        uploaded = SimpleUploadedFile(
            "mismatch.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        upload_id = resp.data["upload_id"]

        # 분석 완료
        notify_analysis_complete(upload_id, {"source_type": "excel", "summary": "불일치 테스트", "errors": []})

        # patch plan 생성
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
            {"prompt": "셀 교체 테스트"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        version_id = resp.data["version_id"]
        changes = resp.data["changes"]

        change_ok_id = next(c["id"] for c in changes if c["operation_id"] == "op_mismatch_001")
        change_fail_id = next(c["id"] for c in changes if c["operation_id"] == "op_mismatch_002")

        # 전부 accept-all (reject 없이 두 change 모두 applied로)
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 2)

        # patch 트리거 — 동기 실행
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/patch/",
        )
        self.assertEqual(resp.status_code, 202)

        # DB 상태 검증
        ok_change = DocumentChange.objects.get(pk=change_ok_id)
        fail_change = DocumentChange.objects.get(pk=change_fail_id)
        version = DocumentVersion.objects.get(pk=version_id)

        # accept-all이 applied로 만들었지만, patcher가 불일치 감지 후 failed로 재기록
        self.assertEqual(ok_change.status, DocumentChange.Status.APPLIED, "정상 change는 applied 유지")
        self.assertEqual(fail_change.status, DocumentChange.Status.FAILED, "불일치 change는 failed")
        self.assertEqual(version.status, DocumentVersion.Status.READY, "하나라도 성공했으므로 version은 ready")

        # 다운로드 XLSX 검증
        resp = self.client.get(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/file/",
        )
        self.assertEqual(resp.status_code, 200)
        file_bytes = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
        self.assertEqual(_xlsx_cell_value(file_bytes, "정산내역", "A2"), "2026-01-01", "성공 change가 반영됨")
        self.assertEqual(_xlsx_cell_value(file_bytes, "정산내역", "C3"), "실제값", "실패 change는 원본 유지")


# ── regression: 동일 upload에 버전 두 번 생성 ────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxE2EVersionNumberRegressionTest(TestCase):
    """
    동일 upload에 generate-patch-plan을 두 번 호출할 때:
      - version_number가 자동으로 증가한다 (v1=original, v2=첫 번째 draft, v3=두 번째 draft)
      - 첫 번째 버전의 patch 완료 후 artifact_file과 status는 두 번째 버전 생성에 영향받지 않는다
    """

    _PLAN_V2 = _patch_plan([
        {
            "operation_id": "op_reg_v2",
            "format": "excel",
            "operation": "replace_cell",
            "title": "v2 A2 교체",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "v2 테스트",
            "confidence": 0.95,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value"},
            "risk": {"level": "low"},
        },
    ])

    _PLAN_V3 = _patch_plan([
        {
            "operation_id": "op_reg_v3",
            "format": "excel",
            "operation": "replace_cell",
            "title": "v3 A2 교체",
            "original": "20260101",
            "replacement": "v3-2026-01-01",
            "reason": "v3 테스트",
            "confidence": 0.88,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value"},
            "risk": {"level": "low"},
        },
    ])

    def setUp(self):
        self.user = _make_user("e2e_regression_user")
        self.client = _authed(self.user)

    @patch("apps.documents.views.current_app.send_task")
    def test_second_version_has_incremented_number_and_does_not_affect_first(self, mock_send_task):
        """두 번째 버전 생성 시 version_number 자동 증가, 첫 버전 artifact 영향 없음."""
        mock_send_task.return_value = MagicMock(id="fake-task-reg")

        # 업로드 + 분석 완료
        xlsx_bytes = _make_xlsx_bytes(
            sheet_name="정산내역",
            data={"A2": "20260101"},
        )
        uploaded = SimpleUploadedFile(
            "regression.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        upload_id = resp.data["upload_id"]
        notify_analysis_complete(upload_id, {"source_type": "excel", "summary": "회귀 테스트", "errors": []})

        # ── 첫 번째 버전 전체 처리 ────────────────────────────────────────
        with patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=self._PLAN_V2):
            resp = self.client.post(
                f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
                {"prompt": "v2 교체"},
                format="json",
            )
        self.assertEqual(resp.status_code, 201)
        version_id_v2 = resp.data["version_id"]
        changes_v2 = resp.data["changes"]

        # v2: accept-all → patch
        self.client.post(f"/api/v1/uploads/{upload_id}/versions/{version_id_v2}/changes/accept-all/")
        self.client.post(f"/api/v1/uploads/{upload_id}/versions/{version_id_v2}/patch/")

        v2 = DocumentVersion.objects.get(pk=version_id_v2)
        self.assertEqual(v2.version_number, 2, "첫 번째 draft는 version_number=2여야 한다")
        self.assertEqual(v2.status, DocumentVersion.Status.READY)
        artifact_name_v2 = v2.artifact_file.name
        self.assertTrue(default_storage.exists(artifact_name_v2), "v2 artifact_file이 storage에 존재해야 한다")

        # ── 두 번째 버전 생성 ─────────────────────────────────────────────
        with patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=self._PLAN_V3):
            resp = self.client.post(
                f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
                {"prompt": "v3 교체"},
                format="json",
            )
        self.assertEqual(resp.status_code, 201)
        version_id_v3 = resp.data["version_id"]

        v3 = DocumentVersion.objects.get(pk=version_id_v3)
        self.assertEqual(v3.version_number, 3, "두 번째 draft는 version_number=3이어야 한다")
        self.assertEqual(v3.status, DocumentVersion.Status.DRAFT, "v3는 아직 draft 상태")

        # v2 artifact와 status가 v3 생성에 영향받지 않았는지 확인
        v2.refresh_from_db()
        self.assertEqual(v2.status, DocumentVersion.Status.READY, "v3 생성 후에도 v2 status는 ready 유지")
        self.assertTrue(
            default_storage.exists(artifact_name_v2),
            "v3 생성 후에도 v2 artifact_file이 storage에 존재해야 한다",
        )

        # 버전 목록 조회 — 3개 버전(original, draft_v2, draft_v3) 확인
        resp = self.client.get(f"/api/v1/uploads/{upload_id}/versions/")
        self.assertEqual(resp.status_code, 200)
        version_numbers = [v["version_number"] for v in resp.data]
        self.assertEqual(sorted(version_numbers), [1, 2, 3], "버전 목록에 1·2·3이 모두 존재해야 한다")


# ── 업무 시나리오: 매출표 헤더 강조 + 표시 형식 + 합계 수식 ─────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class XlsxE2ESalesScenarioTest(TestCase):
    """
    roadmap v1 6.Phase5절 대표 시나리오:
      업로드된 매출표에서 1) 헤더를 강조하고 2) 금액 열 표시 형식을 정리하고
      3) 합계 셀에 수식을 넣고 4) 수정본을 다운로드한다.

    네 번째 operation(op_sales_004)은 의도적으로 허용되지 않은 number_format을 사용해
    개별 change 실패로 격리되는지, 나머지 세 operation은 정상 적용되는지 함께 검증한다.

    XLSX 레이아웃 (sheet="정산내역"):
      A1:D1 = 헤더("항목"/"수량"/"단가"/"금액")
      A2:D2 = "사무용품"/10/1000/10000
      D5    = 합계 대상(수식 설정 전 비어 있음)
    """

    _SALES_PLAN = _patch_plan([
        {
            "operation_id": "op_sales_001",
            "format": "excel",
            "operation": "set_cell_style",
            "title": "표 헤더 강조",
            "reason": "헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.",
            "confidence": 0.9,
            "anchor": {"type": "cell_range", "sheet": "정산내역", "range": "A1:D1"},
            "expected_context": {
                "sample_values": {"A1": "항목", "D1": "금액"},
                "non_empty_cells": ["A1", "B1", "C1", "D1"],
            },
            "patch": {"font_bold": True},
            "risk": {"level": "low"},
        },
        {
            "operation_id": "op_sales_002",
            "format": "excel",
            "operation": "set_number_format",
            "title": "금액 열 표시 형식 정리",
            "reason": "금액이 콤마 없이 표시되어 자릿수를 읽기 어렵습니다.",
            "confidence": 0.88,
            "anchor": {"type": "cell_range", "sheet": "정산내역", "range": "D2:D2"},
            "expected_context": {
                "sample_values": {"D2": "10000"},
                "non_empty_cells": ["D2"],
            },
            "patch": {"number_format": "#,##0원"},
            "risk": {"level": "low"},
        },
        {
            "operation_id": "op_sales_003",
            "format": "excel",
            "operation": "set_formula",
            "title": "금액 합계 셀 계산",
            "reason": "합계 행이 비어 있어 합계를 채워달라는 요청입니다.",
            "confidence": 0.82,
            "anchor": {"type": "cell", "sheet": "정산내역", "cell": "D5"},
            "expected_context": {
                "sample_values": {"D2": "10000"},
                "non_empty_cells": ["D2"],
            },
            "patch": {"formula": "=SUM(D2:D2)"},
            "risk": {"level": "low"},
        },
        {
            # 의도적으로 허용되지 않은 number_format — 개별 실패 격리 검증용
            "operation_id": "op_sales_004",
            "format": "excel",
            "operation": "set_number_format",
            "title": "수량 열 표시 형식 정리(잘못된 patch)",
            "reason": "허용되지 않은 형식을 사용한 실패 시나리오",
            "confidence": 0.5,
            "anchor": {"type": "cell_range", "sheet": "정산내역", "range": "B2:B2"},
            "expected_context": {
                "sample_values": {"B2": "10"},
                "non_empty_cells": ["B2"],
            },
            "patch": {"number_format": "0.000"},
            "risk": {"level": "low"},
        },
    ])

    def setUp(self):
        self.user = _make_user("e2e_sales_user")
        self.client = _authed(self.user)

    @patch("apps.documents.services.patch_plan._generate_patch_plan")
    @patch("apps.documents.views.current_app.send_task")
    def test_sales_table_scenario_partial_failure_preserves_success(self, mock_send_task, mock_gen_plan):
        """헤더 강조·표시 형식·수식은 성공, 잘못된 number_format은 개별 실패로 격리된다."""
        mock_send_task.return_value = MagicMock(id="fake-sales-task-id")
        mock_gen_plan.return_value = self._SALES_PLAN

        # ── 1. 업로드 ───────────────────────────────────────────────────────
        xlsx_bytes = _make_xlsx_bytes(
            sheet_name="정산내역",
            data={
                "A1": "항목", "B1": "수량", "C1": "단가", "D1": "금액",
                "A2": "사무용품", "B2": 10, "C2": 1000, "D2": 10000,
            },
        )
        uploaded = SimpleUploadedFile(
            "sales.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post("/api/v1/uploads/", {"file": uploaded}, format="multipart")
        self.assertEqual(resp.status_code, 202)
        upload_id = resp.data["upload_id"]

        # ── 2. 분석 완료 시뮬레이션 ─────────────────────────────────────────
        notify_analysis_complete(upload_id, {
            "source_type": "excel", "summary": "매출표 수정 요청", "errors": [],
        })

        # ── 3. patch plan 생성 ──────────────────────────────────────────────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/generate-patch-plan/",
            {"prompt": "헤더 강조하고 금액 표시 형식 정리하고 합계 셀에 수식 넣어줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        version_id = resp.data["version_id"]
        changes = resp.data["changes"]
        self.assertEqual(len(changes), 4, "4개 operation이 change로 저장되어야 한다")

        # patch.expected_context 병합이 set_cell_style 외 operation에도 적용됐는지 확인
        style_change = next(c for c in changes if c["operation_id"] == "op_sales_001")
        format_change = next(c for c in changes if c["operation_id"] == "op_sales_002")
        formula_change = next(c for c in changes if c["operation_id"] == "op_sales_003")
        self.assertIn("expected_context", style_change["patch"])
        self.assertIn("expected_context", format_change["patch"])
        self.assertIn("expected_context", formula_change["patch"])

        # ── 4. 전체 accept-all ──────────────────────────────────────────────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 4)

        # ── 5. patch 트리거 (동기 실행) ───────────────────────────────────
        resp = self.client.post(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/patch/",
        )
        self.assertEqual(resp.status_code, 202)

        # ── 6. DB 상태 검증 — 3건 성공, 1건 실패 ────────────────────────────
        version = DocumentVersion.objects.get(pk=version_id)
        self.assertEqual(version.status, DocumentVersion.Status.READY, "일부 성공이므로 ready여야 한다")

        change_map = {c.operation_id: c for c in DocumentChange.objects.filter(version=version)}
        self.assertEqual(change_map["op_sales_001"].status, DocumentChange.Status.APPLIED)
        self.assertEqual(change_map["op_sales_002"].status, DocumentChange.Status.APPLIED)
        self.assertEqual(change_map["op_sales_003"].status, DocumentChange.Status.APPLIED)
        self.assertEqual(
            change_map["op_sales_004"].status, DocumentChange.Status.FAILED,
            "허용되지 않은 number_format은 개별 실패로 격리되어야 한다",
        )

        # ── 7. 버전 목록으로 status 확인 (polling 시뮬레이션) ──────────────
        resp = self.client.get(f"/api/v1/uploads/{upload_id}/versions/")
        self.assertEqual(resp.status_code, 200)
        patched = next(v for v in resp.data if v["id"] == version_id)
        self.assertEqual(patched["status"], "ready")

        # ── 8. artifact 다운로드 및 openpyxl 검증 ───────────────────────────
        resp = self.client.get(
            f"/api/v1/uploads/{upload_id}/versions/{version_id}/file/",
        )
        self.assertEqual(resp.status_code, 200)
        file_bytes = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
        ws = wb["정산내역"]

        self.assertTrue(ws["A1"].font.bold, "헤더 강조(set_cell_style)가 반영되어야 한다")
        self.assertEqual(ws["D2"].number_format, "#,##0원", "금액 표시 형식이 반영되어야 한다")
        self.assertEqual(ws["D5"].value, "=SUM(D2:D2)", "합계 수식이 반영되어야 한다")
        # 실패한 operation의 대상 셀(B2)은 원본 number_format(General)이 유지되어야 한다
        self.assertNotEqual(ws["B2"].number_format, "0.000", "실패한 operation은 반영되지 않아야 한다")
