"""
UsageEvent / record_usage_event 테스트.

커버 범위:
  1. record_usage_event 생성 — FK 객체 전달 시 정상 저장
  2. best-effort 실패 처리 — DB 저장이 예외를 던져도 원래 흐름을 깨지 않고 None 반환
  3. 이번 달 / 본인 필터링 — 대시보드 집계 대상 범위 검증
  4. token_source 판별 — provider_reported / unavailable
  5. patch artifact 실패 이벤트 — PatchResult의 안정된 실패 사유 코드가
     metadata.reason으로 기록됨 (design v1 8절)
"""
import io
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
    UsageEvent,
)
from apps.documents.services.usage import record_usage_event, usage_metadata_from_result

User = get_user_model()

# 파일 저장 격리용 임시 MEDIA_ROOT (patch artifact 테스트에서 업로드 파일 필요)
TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_usage_event_")


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 정리."""
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def _make_user(username="usage_tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_upload_log(user):
    fs, _ = FileStructure.objects.get_or_create(
        hash="usage_event_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="report.xlsx",
        status=UploadLog.Status.DONE,
    )


class RecordUsageEventCreationTest(TestCase):
    """record_usage_event가 FK 객체만으로 UsageEvent를 정상 생성하는지 검증."""

    def setUp(self):
        self.user = _make_user()
        self.upload_log = _make_upload_log(self.user)

    def test_creates_usage_event_with_fk_objects_only(self):
        """user/upload_log FK 객체만 넘겨도 이벤트가 생성된다 (id kwargs 아님)."""
        event = record_usage_event(
            user=self.user,
            upload_log=self.upload_log,
            event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
            status=UsageEvent.Status.SUCCESS,
            metadata={"source": "test"},
        )

        self.assertIsNotNone(event)
        self.assertEqual(UsageEvent.objects.count(), 1)
        saved = UsageEvent.objects.get()
        self.assertEqual(saved.user_id, self.user.pk)
        self.assertEqual(saved.upload_log_id, self.upload_log.pk)
        self.assertEqual(saved.event_type, UsageEvent.EventType.DOCUMENT_ANALYSIS)
        self.assertEqual(saved.status, UsageEvent.Status.SUCCESS)

    def test_total_tokens_property(self):
        """total_tokens는 input_tokens + output_tokens를 반환한다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            input_tokens=120,
            output_tokens=80,
        )
        self.assertEqual(event.total_tokens, 200)


class RecordUsageEventFailureTest(TestCase):
    """DB 저장 실패 시 best-effort로 None을 반환하고 예외를 전파하지 않는지 검증."""

    def setUp(self):
        self.user = _make_user()

    def test_db_error_returns_none_without_raising(self):
        """UsageEvent.objects.create가 예외를 던져도 record_usage_event는 조용히 None을 반환한다."""
        with patch(
            "apps.documents.services.usage.UsageEvent.objects.create",
            side_effect=Exception("db down"),
        ):
            result = record_usage_event(
                user=self.user,
                event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
                status=UsageEvent.Status.SUCCESS,
            )
        self.assertIsNone(result)
        self.assertEqual(UsageEvent.objects.count(), 0)

    def test_malformed_metadata_does_not_raise(self):
        """estimated_cost 등 파싱 불가능한 값이 들어와도 예외 없이 기본값으로 저장된다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
            estimated_cost="not-a-number",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.estimated_cost, Decimal("0"))


class UsageEventFilteringTest(TestCase):
    """월별 / 유저별 필터링 검증 — 대시보드 집계 범위와 동일한 조건."""

    def setUp(self):
        self.user = _make_user("filter_user")
        self.other_user = _make_user("filter_other")

    def _current_month_qs(self, user):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return UsageEvent.objects.filter(user=user, created_at__gte=month_start)

    def test_only_current_user_events_included(self):
        """다른 유저의 이벤트는 필터 결과에 포함되지 않는다."""
        record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        record_usage_event(user=self.other_user, event_type=UsageEvent.EventType.CHAT_QA)

        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user_id, self.user.pk)

    def test_previous_month_events_excluded(self):
        """지난 달 생성된 이벤트는 이번 달 집계에서 제외된다."""
        event = record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        # created_at은 auto_now_add라서 직접 update로 과거 시점으로 이동시킨다.
        past = timezone.now() - timedelta(days=45)
        UsageEvent.objects.filter(pk=event.pk).update(created_at=past)

        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 0)

    def test_current_month_events_included(self):
        """이번 달 생성된 이벤트는 집계에 포함된다."""
        record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 1)


class TokenSourceTest(TestCase):
    """token_source 판별 로직 검증."""

    def setUp(self):
        self.user = _make_user("token_source_user")

    def test_defaults_to_unavailable_without_token_counts(self):
        """토큰 수치가 전혀 없으면 token_source는 UNAVAILABLE."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.UNAVAILABLE)

    def test_provider_reported_when_tokens_present(self):
        """usage 메타데이터에 토큰 수치가 있으면 PROVIDER_REPORTED로 추론된다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            metadata={"usage": {"input_tokens": 100, "output_tokens": 50}},
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.PROVIDER_REPORTED)
        self.assertEqual(event.input_tokens, 100)
        self.assertEqual(event.output_tokens, 50)

    def test_explicit_token_source_overrides_inference(self):
        """token_source가 명시적으로 전달되면 추론값보다 우선한다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            token_source=UsageEvent.TokenSource.ESTIMATED,
            input_tokens=10,
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.ESTIMATED)


class EstimatedCostPricingFallbackTest(TestCase):
    """estimated_cost 미지정 시 pricing.py 가격표로 자동 계산되는지 검증."""

    def setUp(self):
        self.user = _make_user("pricing_fallback_user")

    def test_uses_pricing_table_when_cost_not_provided(self):
        """metadata/estimated_cost 모두 없으면 model+tokens로 pricing.py가 계산한다."""
        from apps.documents.services.pricing import estimate_cost_krw

        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
        )
        expected = estimate_cost_krw("claude-sonnet-4-6", 1000, 500)
        self.assertEqual(event.estimated_cost, expected)
        self.assertGreater(event.estimated_cost, Decimal("0"))

    def test_explicit_estimated_cost_overrides_pricing_table(self):
        """estimated_cost가 명시적으로 전달되면 pricing.py 계산값보다 우선한다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost=Decimal("999"),
        )
        self.assertEqual(event.estimated_cost, Decimal("999"))

    def test_unknown_model_falls_back_to_zero(self):
        """가격표에 없는 모델은 예외 없이 0으로 저장된다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            model="unknown-model-xyz",
            input_tokens=1000,
            output_tokens=500,
        )
        self.assertEqual(event.estimated_cost, Decimal("0"))


class IntentClassificationEventTypeTest(TestCase):
    """EventType.INTENT_CLASSIFICATION 추가 검증 — 의도 분류 LLM 호출 기록용."""

    def test_intent_classification_choice_exists(self):
        self.assertIn(
            "intent_classification",
            dict(UsageEvent.EventType.choices),
        )

    def test_can_record_intent_classification_event(self):
        user = _make_user("intent_classification_user")
        event = record_usage_event(
            user=user,
            event_type=UsageEvent.EventType.INTENT_CLASSIFICATION,
            metadata={"source": "chat"},
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "intent_classification")


class UsageMetadataFromResultTest(TestCase):
    """usage_metadata_from_result 헬퍼 검증."""

    def test_extracts_expected_keys_from_result_dict(self):
        result = {
            "provider": "openai",
            "model": "gpt-x",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "latency_ms": 200,
            "estimated_cost": "1.5",
        }
        metadata = usage_metadata_from_result(result, source="unit_test")
        self.assertEqual(metadata["provider"], "openai")
        self.assertEqual(metadata["model"], "gpt-x")
        self.assertEqual(metadata["usage"], {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(metadata["source"], "unit_test")

    def test_handles_non_dict_result(self):
        """result가 dict가 아니어도 예외 없이 빈 메타데이터를 반환한다."""
        metadata = usage_metadata_from_result(None, source="unit_test")
        self.assertEqual(metadata["provider"], "")
        self.assertEqual(metadata["source"], "unit_test")



class TestUnsupportedScanRecording(TestCase):
    """
    스캔본(미지원) 분석 결과의 UsageEvent 기록 정책 테스트.

    closed-beta-launch-plan-v1-ko.md 결정 16 + 리뷰 발견 1:
      스캔본은 LLM 분석이 수행되지 않았으므로 FAILED + error_code로 기록해
      크레딧 차감에서 제외하고, 수요 관찰(인터뷰 재료)은 가능하게 남긴다.
    """

    def setUp(self):
        self.user = _make_user()
        self.upload_log = _make_upload_log(self.user)

    def _scan_payload(self):
        return {
            "upload_id": self.upload_log.pk,
            "summary": "스캔 문서(이미지 기반)는 아직 지원하지 않아요.",
            "errors": [],
            "source_type": "pdf_image",
            "usage": {"input_tokens": 0, "output_tokens": 0, "token_source": "unavailable"},
            "model": "",
            "provider": "",
        }

    def test_notify_callback_records_scan_as_failed(self):
        """콜백 경로: 스캔본 결과는 FAILED + error_code=unsupported_scan으로 기록된다."""
        from apps.documents.tasks import notify_analysis_complete

        notify_analysis_complete.run(upload_id=self.upload_log.pk, result=self._scan_payload())

        event = UsageEvent.objects.get(upload_log=self.upload_log)
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertEqual(event.metadata.get("error_code"), "unsupported_scan")

    def test_scan_event_does_not_consume_credit(self):
        """스캔본 이벤트는 월간 크레딧 사용량에 포함되지 않는다."""
        from apps.documents.services.usage import get_monthly_credit_status
        from apps.documents.tasks import notify_analysis_complete

        notify_analysis_complete.run(upload_id=self.upload_log.pk, result=self._scan_payload())

        credit = get_monthly_credit_status(self.user)
        self.assertEqual(credit["used"], 0)

    def test_normal_analysis_still_recorded_as_success(self):
        """[회귀] 일반 분석 결과는 기존대로 SUCCESS로 기록된다."""
        from apps.documents.tasks import notify_analysis_complete

        payload = {**self._scan_payload(), "source_type": "pdf_digital", "summary": "분석 완료"}
        notify_analysis_complete.run(upload_id=self.upload_log.pk, result=payload)

        event = UsageEvent.objects.get(upload_log=self.upload_log)
        self.assertEqual(event.status, UsageEvent.Status.SUCCESS)


# ── patch artifact 실패 사유 코드 기록 ────────────────────────────────────────


def _docx_two_matches_bytes() -> bytes:
    """같은 문구가 두 단락에 나오는 DOCX (ambiguous_anchor 유발용)."""
    from docx import Document
    doc = Document()
    doc.add_paragraph("계약금액 1,000원")
    doc.add_paragraph("비고: 계약금액은 부가세 포함")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf_cjk_bytes(text: str) -> bytes:
    """CJK 텍스트 한 줄짜리 단일 페이지 PDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=12, fontname="korea-s", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PatchArtifactFailureCodeTest(TestCase):
    """
    patch artifact 생성 실패 시 UsageEvent metadata에 안정된 실패 사유 코드가
    기록되는지 검증 (design v1 8절 — 실패 사유 코드 정리).

    조기 실패 경로(source_file_missing/unsupported_format 등)는 이미 metadata.reason에
    코드를 기록한다 — 여기서는 render/persist까지 진행된 뒤의 실패가 PatchResult
    항목의 code를 물려받는지 확인한다.
    """

    def setUp(self):
        self.user = _make_user("patch_failure_code_user")

    def _make_patch_fixture(self, source_type, filename, file_bytes, hash_val):
        fs, _ = FileStructure.objects.get_or_create(
            hash=hash_val,
            defaults={"source_type": source_type, "column_schema": []},
        )
        upload = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename=filename,
            status=UploadLog.Status.DONE,
        )
        upload.file.save(filename, ContentFile(file_bytes), save=True)
        version = DocumentVersion.objects.create(
            upload_log=upload,
            version_number=2,
            status=DocumentVersion.Status.DRAFT,
            label="draft",
            created_by=self.user,
        )
        return upload, version

    def _make_applied_change(self, version, operation_id, operation, anchor, original, replacement):
        return DocumentChange.objects.create(
            version=version,
            operation_id=operation_id,
            operation=operation,
            title="테스트 변경",
            original=original,
            replacement=replacement,
            anchor=anchor,
            confidence=0.9,
            status=DocumentChange.Status.APPLIED,
        )

    def _artifact_event(self):
        return UsageEvent.objects.get(
            event_type=UsageEvent.EventType.PATCH_ARTIFACT_GENERATION,
        )

    def test_docx_ambiguous_match_records_ambiguous_anchor_reason(self):
        """DOCX 다중 매치 → NEEDS_CONFIRMATION 종료 → 이벤트 FAILED + reason=ambiguous_anchor."""
        from apps.documents.tasks import patch_document_version

        upload, version = self._make_patch_fixture(
            "docx", "ambiguous.docx", _docx_two_matches_bytes(), "usage_docx_ambiguous_hash",
        )
        self._make_applied_change(
            version,
            operation_id="op_usage_docx_dup",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "계약금액"},
            original="계약금액",
            replacement="총계약금액",
        )
        patch_document_version(version.pk)

        event = self._artifact_event()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertEqual(
            event.metadata.get("reason"),
            "ambiguous_anchor",
            "위치 확인 대기로 끝난 patch 이벤트에는 reason=ambiguous_anchor가 기록되어야 한다",
        )

    def test_pdf_render_validation_failure_records_reason_code(self):
        """PDF render 검증 실패 → 이벤트 FAILED + reason=render_validation_failed."""
        from apps.documents.tasks import patch_document_version

        upload, version = self._make_patch_fixture(
            FileStructure.SourceType.PDF, "validate.pdf", _pdf_cjk_bytes("접수번호"),
            "usage_pdf_validation_hash",
        )
        self._make_applied_change(
            version,
            operation_id="op_usage_pdf_val",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "접수번호", "page": 1, "occurrence": 1},
            original="접수번호",
            replacement="접수완료",
        )

        def _redact_without_insert(page, rect, change):
            # replacement 삽입 없이 redaction만 수행 — 검증 실패 유발
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

        with patch(
            "apps.documents.patcher._apply_pdf_redact_overlay",
            side_effect=_redact_without_insert,
        ):
            patch_document_version(version.pk)

        event = self._artifact_event()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertEqual(event.metadata.get("reason"), "render_validation_failed")

    def test_failure_without_stable_code_omits_reason_key(self):
        """[경계] 코드가 없는 실패(대상 텍스트 없음)는 reason 키를 기록하지 않는다."""
        from apps.documents.tasks import patch_document_version

        upload, version = self._make_patch_fixture(
            "docx", "notfound.docx", _docx_two_matches_bytes(), "usage_docx_notfound_hash",
        )
        self._make_applied_change(
            version,
            operation_id="op_usage_docx_notfound",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "존재하지 않는 문구"},
            original="존재하지 않는 문구",
            replacement="무관",
        )
        patch_document_version(version.pk)

        event = self._artifact_event()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertNotIn(
            "reason", event.metadata,
            "안정 코드가 없는 실패에 임의 reason이 기록되면 안 된다",
        )
