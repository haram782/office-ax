"""
전체 적용(accept-all) API 테스트.

POST /api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/

커버 범위:
  happy path  - 충돌 없는 pending 변경 전부 applied
  boundary    - anchor가 빈 dict인 변경들은 그룹핑 없이 전부 applied
  boundary    - confidence 동점 시 operation_id 오름차순 승자 결정
  failure     - 타인 소유 접근 403, version_id가 upload에 속하지 않으면 404
  regression  - 이미 applied/rejected인 change는 영향받지 않음
  regression  - pending 0개 → 200 + applied=[] rejected=[]
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.documents.models import DocumentChange, DocumentVersion, FileStructure, UploadLog

User = get_user_model()


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

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


def _make_version(upload, user, version_number=2):
    return DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=DocumentVersion.Status.DRAFT,
        label="draft",
        created_by=user,
    )


def _make_change(version, operation_id, anchor, confidence=0.9,
                  status=DocumentChange.Status.PENDING, reason="기존 사유"):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        operation="replace_cell",
        title="테스트",
        original="원본",
        replacement="수정",
        reason=reason,
        anchor=anchor,
        confidence=confidence,
        status=status,
    )


def _url(upload_id, version_id):
    return f"/api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/"


# ── 테스트 ────────────────────────────────────────────────────────────────────


class AcceptAllNoConflictTest(TestCase):
    """충돌 없는 pending 변경 → 전부 applied."""

    def setUp(self):
        self.user = _make_user("accept_all_user")
        self.upload = _make_upload(self.user, "accept_all_hash1")
        self.version = _make_version(self.upload, self.user)

    def test_three_pending_changes_no_conflict_all_applied(self):
        """서로 다른 anchor를 가진 pending 변경 3개 → 전부 applied."""
        c1 = _make_change(self.version, "op_001", {"type": "cell", "cell": "A1"})
        c2 = _make_change(self.version, "op_002", {"type": "cell", "cell": "B1"})
        c3 = _make_change(self.version, "op_003", {"type": "cell", "cell": "C1"})

        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 3)
        self.assertEqual(len(resp.data["rejected"]), 0)

        for c in (c1, c2, c3):
            c.refresh_from_db()
            self.assertEqual(c.status, DocumentChange.Status.APPLIED)


class AcceptAllConflictTest(TestCase):
    """같은 anchor를 가리키는 pending 변경 충돌 처리."""

    def setUp(self):
        self.user = _make_user("conflict_user")
        self.upload = _make_upload(self.user, "accept_all_hash2")
        self.version = _make_version(self.upload, self.user)

    def test_higher_confidence_wins_lower_rejected_with_reason(self):
        """같은 anchor, confidence 다름 → 높은 쪽만 applied, 낮은 쪽 rejected + 사유 추가."""
        anchor = {"type": "cell", "cell": "D12"}
        low = _make_change(self.version, "op_low", anchor, confidence=0.5, reason="낮은 신뢰도 사유")
        high = _make_change(self.version, "op_high", anchor, confidence=0.95, reason="높은 신뢰도 사유")

        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 1)
        self.assertEqual(len(resp.data["rejected"]), 1)

        high.refresh_from_db()
        low.refresh_from_db()

        self.assertEqual(high.status, DocumentChange.Status.APPLIED)
        self.assertEqual(low.status, DocumentChange.Status.REJECTED)
        self.assertIn("높은 신뢰도 변경 채택", low.reason)
        self.assertIn("낮은 신뢰도 사유", low.reason, "기존 reason은 보존되어야 한다")

    def test_confidence_tie_breaks_by_operation_id_ascending(self):
        """같은 anchor, confidence 동점 → operation_id 오름차순 승자 결정."""
        anchor = {"type": "cell", "cell": "E5"}
        # operation_id 오름차순: op_a < op_b
        c_a = _make_change(self.version, "op_a", anchor, confidence=0.8)
        c_b = _make_change(self.version, "op_b", anchor, confidence=0.8)

        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        c_a.refresh_from_db()
        c_b.refresh_from_db()

        self.assertEqual(c_a.status, DocumentChange.Status.APPLIED, "operation_id가 더 빠른 쪽이 승자여야 한다")
        self.assertEqual(c_b.status, DocumentChange.Status.REJECTED)

    def test_empty_anchor_changes_not_grouped(self):
        """anchor가 빈 dict인 변경 여러 개 → 그룹핑 없이 전부 applied."""
        c1 = _make_change(self.version, "op_e1", {})
        c2 = _make_change(self.version, "op_e2", {})

        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 2)
        self.assertEqual(len(resp.data["rejected"]), 0)

        c1.refresh_from_db()
        c2.refresh_from_db()
        self.assertEqual(c1.status, DocumentChange.Status.APPLIED)
        self.assertEqual(c2.status, DocumentChange.Status.APPLIED)


class AcceptAllRegressionTest(TestCase):
    """기존 상태 보존 및 빈 입력 처리."""

    def setUp(self):
        self.user = _make_user("regression_user")
        self.upload = _make_upload(self.user, "accept_all_hash3")
        self.version = _make_version(self.upload, self.user)

    def test_already_applied_or_rejected_changes_not_affected(self):
        """이미 applied/rejected 상태인 change는 영향받지 않는다 (pending만 대상)."""
        anchor = {"type": "cell", "cell": "F1"}
        already_applied = _make_change(
            self.version, "op_done", anchor, confidence=0.99,
            status=DocumentChange.Status.APPLIED,
        )
        already_rejected = _make_change(
            self.version, "op_gone", {"type": "cell", "cell": "G1"},
            status=DocumentChange.Status.REJECTED,
        )
        pending = _make_change(self.version, "op_new", {"type": "cell", "cell": "H1"})

        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["applied"]), 1)

        already_applied.refresh_from_db()
        already_rejected.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(already_applied.status, DocumentChange.Status.APPLIED)
        self.assertEqual(already_rejected.status, DocumentChange.Status.REJECTED)
        self.assertEqual(pending.status, DocumentChange.Status.APPLIED)

    def test_no_pending_changes_returns_empty_lists(self):
        """pending 변경이 0개 → 200 + applied=[] rejected=[]."""
        resp = _authed(self.user).post(_url(self.upload.pk, self.version.pk))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["applied"], [])
        self.assertEqual(resp.data["rejected"], [])


class AcceptAllAccessControlTest(TestCase):
    """소유권 검증 테스트."""

    def setUp(self):
        self.user = _make_user("owner_user")
        self.other = _make_user("other_user")
        self.upload = _make_upload(self.user, "accept_all_hash4")
        self.version = _make_version(self.upload, self.user)
        _make_change(self.version, "op_001", {"type": "cell", "cell": "A1"})

    def test_other_user_gets_403(self):
        """타인 소유 upload/version 접근 → 403."""
        resp = _authed(self.other).post(_url(self.upload.pk, self.version.pk))
        self.assertEqual(resp.status_code, 403)

    def test_version_not_belonging_to_upload_returns_404(self):
        """version_id가 해당 upload_log에 속하지 않는 경우 → 404."""
        other_upload = _make_upload(self.user, "accept_all_hash5")
        other_version = _make_version(other_upload, self.user, version_number=2)

        # self.upload의 id와 other_version의 id 조합 → upload_log 불일치
        resp = _authed(self.user).post(_url(self.upload.pk, other_version.pk))
        self.assertEqual(resp.status_code, 404)
