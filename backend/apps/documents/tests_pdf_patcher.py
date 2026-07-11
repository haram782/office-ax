"""
PDF annotate / redact_overlay / replace_text 패처 테스트.

커버 범위:
  patch_document_version Celery 태스크 (동기 직접 호출)
  - pdf_bbox anchor + annotate → 하이라이트 주석이 생성된다
  - text_match anchor + annotate → search_for로 rect를 찾아 주석이 생성된다
  - pdf_bbox anchor + redact_overlay → artifact에 replacement 텍스트가 포함된다
  - text_match anchor + replace_text → 짧은 한글 텍스트가 치환되고 추출 가능하다
  - anchor 해석 실패(텍스트 없음) → change.status=failed
  - 모든 항목 실패 → version.status=failed
  - 하나라도 성공 → version.status=ready + artifact_file 생성
  - post-render 검증 (design v1 7.1절 invariant 1~2) → 검증 실패 시 artifact 없이
    code=render_validation_failed로 멈춤
"""
import io
import tempfile
from unittest.mock import patch as mock_patch

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


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 정리."""
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _build_pdf_bytes(text: str = "샘플 텍스트") -> bytes:
    """
    지정 텍스트가 포함된 단일 페이지 PDF 바이트를 fitz로 생성한다.

    fitz 기본 내장 폰트(helv)는 라틴 문자만 지원하므로
    CJK 텍스트는 display 깨짐이 발생할 수 있으나 bytes 인코딩은 유효하다.
    text_match anchor로 CJK 원문을 검색해야 하는 테스트는
    _build_pdf_bytes_cjk를 사용한다.
    """
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 크기
    # Helvetica 기본 폰트로 텍스트 삽입
    page.insert_text((72, 100), text, fontsize=12, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _build_pdf_bytes_cjk(text: str) -> bytes:
    """
    CJK 문자가 포함된 텍스트를 "korea-s" 폰트로 삽입한 단일 페이지 PDF를 생성한다.

    Helvetica는 한글 글리프가 없어 삽입해도 검색 불가능한 텍스트가 되므로
    text_match anchor로 한글 원문을 찾아야 하는 테스트는 이 헬퍼를 사용한다.
    """
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 크기
    page.insert_text((72, 100), text, fontsize=12, fontname="korea-s", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_upload(user, filename, file_bytes, hash_val=None):
    _hash = hash_val or f"hash_pdf_{filename}"
    fs, _ = FileStructure.objects.get_or_create(
        hash=_hash,
        defaults={"source_type": FileStructure.SourceType.PDF, "column_schema": []},
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


# ── 테스트 클래스 ──────────────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfAnnotateTest(TestCase):
    """PDF annotate 패처 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_annotate_user")
        self.pdf_bytes = _build_pdf_bytes("Hello World")
        self.upload = _make_upload(self.user, "sample.pdf", self.pdf_bytes, "pdf_ann_hash")
        self.version = _make_version(self.upload, self.user)

    def test_pdf_bbox_annotate_sets_version_ready(self):
        """pdf_bbox anchor + annotate → version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_ann_01",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
                "target_text": "Hello World",
            },
            original="",
            replacement="검토 필요",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "pdf_bbox annotate 성공 후 version.status는 READY여야 한다",
        )

    def test_pdf_bbox_annotate_returns_bytes(self):
        """pdf_bbox anchor + annotate → render_pdf가 bytes를 반환한다."""
        from apps.documents.patcher import collect_applied_changes, render_pdf

        _make_change(
            self.version,
            operation_id="op_ann_02",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
                "target_text": "Hello World",
            },
            replacement="검토 완료",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_pdf(original_bytes, changes)

        self.assertIsInstance(result.output_bytes, (bytes, bytearray), "annotate 후 render_pdf는 bytes를 반환해야 한다")

    def test_text_match_annotate_sets_version_ready(self):
        """text_match anchor + annotate → search_for로 rect를 찾아 version.status=ready."""
        _make_change(
            self.version,
            operation_id="op_ann_03",
            operation="annotate",
            anchor={
                "type": "text_match",
                "target_text": "Hello World",
                "page": 1,
                "occurrence": 1,
            },
            replacement="텍스트 확인 필요",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "text_match annotate 성공 후 version.status는 READY여야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfRedactOverlayTest(TestCase):
    """PDF redact_overlay 패처 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_redact_user")
        self.pdf_bytes = _build_pdf_bytes("2025 08 11")
        self.upload = _make_upload(self.user, "redact.pdf", self.pdf_bytes, "pdf_redact_hash")
        self.version = _make_version(self.upload, self.user)

    def test_pdf_bbox_redact_overlay_sets_version_ready(self):
        """pdf_bbox anchor + redact_overlay → version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_redact_01",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 200, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="2025-08-11",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "redact_overlay 성공 후 version.status는 READY여야 한다",
        )

    def test_redact_overlay_artifact_contains_replacement(self):
        """redact_overlay 후 render_pdf 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        import fitz
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        _make_change(
            self.version,
            operation_id="op_redact_02",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 200, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="2025-08-11",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        patch_result = render_pdf(original_bytes, changes)
        persist_patch_result(self.version, patch_result, "pdf", changes)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)
        result_bytes = patch_result.output_bytes
        self.assertGreater(len(result_bytes), 0, "render_pdf는 bytes를 반환해야 한다")

        doc = fitz.open(stream=result_bytes, filetype="pdf")
        full_text = "".join(page.get_text() for page in doc)
        doc.close()

        self.assertIn(
            "2025-08-11",
            full_text,
            "반환 bytes PDF에 replacement 텍스트가 포함되어야 한다",
        )

    def test_redact_overlay_cjk_replacement_is_not_garbled(self):
        """
        한글 replacement 텍스트가 깨지지 않고 그대로 추출되어야 한다.

        PyMuPDF 1.24.5에서 fitz.Font("cjk")를 insert_text(font=...)로 넘기면
        TypeError가 발생해 Helvetica로 fallback되는데, Helvetica는 한글 글리프가
        없어 텍스트가 "····"처럼 완전히 깨진다. fontname="korea-s"를 써야 한다.
        """
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        _make_change(
            self.version,
            operation_id="op_redact_cjk_01",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 300, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="계약일자 변경",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        patch_result = render_pdf(original_bytes, changes)
        persist_patch_result(self.version, patch_result, "pdf", changes)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        result_bytes = patch_result.output_bytes
        import fitz
        doc = fitz.open(stream=result_bytes, filetype="pdf")
        full_text = "".join(page.get_text() for page in doc)
        doc.close()

        self.assertIn(
            "계약일자",
            full_text,
            "한글 replacement 텍스트가 Helvetica fallback으로 깨지지 않고 추출돼야 한다",
        )

    def test_redact_overlay_cjk_replacement_font_is_embedded(self):
        """
        [버그 수정] 한글 replacement에 쓰인 폰트가 PDF에 실제로 임베드돼야 한다.

        fontname="korea-s"는 텍스트 추출은 되지만 실제 글리프 데이터를 PDF에
        담지 않는 "참조 전용" 폰트다(뷰어가 시스템에 Batang 폰트를 갖고 있다고
        가정) — Adobe 등 데스크톱 뷰어는 시스템 폰트로 대체해 보여주지만, 브라우저
        pdf.js는 대체하지 못해 텍스트가 완전히 투명하게 렌더링된다. 이 회귀는
        get_text() 추출만으로는 못 잡으므로(추출은 항상 성공) get_fonts()로
        실제 임베드 여부(ext != 'n/a')를 직접 확인해야 한다.
        """
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        _make_change(
            self.version,
            operation_id="op_redact_cjk_embed_01",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 300, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="2026년 7월 1일",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        patch_result = render_pdf(original_bytes, changes)

        import fitz
        doc = fitz.open(stream=patch_result.output_bytes, filetype="pdf")
        fonts = [f for page in doc for f in page.get_fonts()]
        doc.close()

        cjk_fonts = [f for f in fonts if f[3] not in ("Helvetica",)]
        self.assertTrue(cjk_fonts, "한글 삽입에 쓰인 폰트가 있어야 한다")
        for xref, ext, ftype, basefont, name, encoding in cjk_fonts:
            self.assertNotEqual(
                ext, "n/a",
                f"'{basefont}' 폰트가 임베드되지 않았다 (참조 전용) — "
                "pdf.js 등 브라우저 뷰어에서 텍스트가 안 보이는 원인",
            )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfReplaceTextTest(TestCase):
    """PDF replace_text 패처 테스트 (readable PDF 짧은 텍스트 치환)."""

    def setUp(self):
        self.user = _make_user("pdf_replace_user")
        # 단일 한글 단어를 target_text로 사용한다 — 여러 단어를 섞으면
        # PyMuPDF search_for()가 단어 경계마다 rect를 분할 반환해 occurrence
        # 카운팅이 불안정해지므로 이 테스트의 목적(짧은 한글 치환 검증)에는
        # 단일 단어 anchor가 적합하다.
        self.pdf_bytes = _build_pdf_bytes_cjk("접수번호")
        self.upload = _make_upload(self.user, "replace.pdf", self.pdf_bytes, "pdf_replace_hash")
        self.version = _make_version(self.upload, self.user)

    def test_replace_text_via_task_sets_version_ready(self):
        """
        patch_document_version 태스크로 text_match anchor + replace_text 처리 시
        version.status=ready가 되어야 한다.

        PatchPlan 스키마(patch-plan-schema-v0-ko.md 6절)는 PDF readable의
        replace_text를 "짧은 overlay 치환"으로 명시적으로 허용하고,
        render_pdf는 annotate가 아닌 operation을 모두 redact_overlay 방식으로
        처리하므로 collect 단계의 operation 필터에도 replace_text가 포함되어야 한다.
        """
        _make_change(
            self.version,
            operation_id="op_replace_01",
            operation="replace_text",
            anchor={
                "type": "text_match",
                "target_text": "접수번호",
                "page": 1,
                "occurrence": 1,
            },
            original="접수번호",
            replacement="접수완료",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "text_match + replace_text 성공 후 version.status는 READY여야 한다",
        )

    def test_replace_text_korean_short_replacement_is_extractable(self):
        """text_match anchor로 찾은 짧은 한글 텍스트를 replace_text로 교체하면 깨지지 않고 추출된다."""
        import fitz

        _make_change(
            self.version,
            operation_id="op_replace_02",
            operation="replace_text",
            anchor={
                "type": "text_match",
                "target_text": "접수번호",
                "page": 1,
                "occurrence": 1,
            },
            original="접수번호",
            replacement="접수완료",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        with self.version.artifact_file.open("rb") as f:
            result_bytes = f.read()
        doc = fitz.open(stream=result_bytes, filetype="pdf")
        full_text = "".join(page.get_text() for page in doc)
        doc.close()

        self.assertIn(
            "접수완료",
            full_text,
            "replace_text로 치환된 한글 텍스트가 깨지지 않고 추출돼야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
def _build_pdf_bytes_fragmented_field() -> bytes:
    """
    라벨("년 월 일")을 먼저 그리고 채워진 값("2026 6 27")을 나중에
    라벨 사이사이 위치에 그린 합성 PDF를 만든다.

    실제 버그 문서와 동일한 패턴: search_for("2026 6 27")가 "2026","6","27"
    세 조각(rect)으로 쪼개져 반환된다 — 코드가 첫 조각만 쓰면 일부만
    지워지고 나머지는 겹쳐 그려진다.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((235, 715), "년", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((295, 715), "월", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((345, 715), "일", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((190, 715), "2026", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((265, 715), "6", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((315, 715), "27", fontsize=11, fontname="helv", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class PdfFragmentedAnchorTest(TestCase):
    """
    text_match 앵커가 여러 조각(rect)으로 쪼개지는 경우 테스트 (버그 신고 2026-07-10).

    실사용 문서에서 "신청일자를 2026년 7월 1일로" 요청이 "반영됨"으로
    처리됐는데도 실제로는 "2026 7년 6월 27일"처럼 새 값과 옛 값이 겹쳐
    렌더링됐다 — search_for()가 반환한 여러 조각 중 첫 조각만 지우고
    그렸기 때문이다.
    """

    def setUp(self):
        self.user = _make_user("pdf_fragment_user")
        self.pdf_bytes = _build_pdf_bytes_fragmented_field()
        self.upload = _make_upload(self.user, "fragment.pdf", self.pdf_bytes, "pdf_fragment_hash")
        self.version = _make_version(self.upload, self.user)

    def test_fragmented_match_replaces_entire_span_not_first_fragment_only(self):
        """
        [버그 수정] 여러 조각으로 쪼개진 text_match도 전체 범위가 교체돼야 한다.

        수정 전에는 "2026" 조각만 지워지고 새 텍스트가 좁은 그 영역에만
        그려져 "6","27","년","월" 옛 글자와 겹쳐 보였다(실사용 문서에서
        "2026 7년  6월  27일"처럼 신구 텍스트가 뒤섞여 렌더링된 원인).

        범위 밖 참고: target_text("2026 6 27")에 포함되지 않은, 매치
        바로 뒤에 인접한 정적 라벨(이 테스트의 "일")이 redaction 밖에
        남는 것은 이번 수정의 범위가 아니다 — search_for()가 PDF 내부
        원시 순서로 동작해 읽기순서 문자열("2026년 6월 27일")로는 애초에
        매치되지 않는, parse_pdf() 읽기순서 재구성과는 별개인 더 깊은
        제약이다(gap_structural_edit_unsupported 계열 후속 과제로 기록).
        """
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        _make_change(
            self.version,
            operation_id="op_frag_01",
            operation="redact_overlay",
            anchor={"type": "text_match", "occurrence": 1, "target_text": "2026 6 27"},
            original="2026 6 27",
            replacement="2026년 7월 1일",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        patch_result = render_pdf(self.pdf_bytes, changes)
        persist_patch_result(self.version, patch_result, "pdf", changes)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        import fitz
        doc = fitz.open(stream=patch_result.output_bytes, filetype="pdf")
        words = doc[0].get_text("words")
        doc.close()

        # target_text("2026 6 27") 내부에 있던 옛 값·라벨 조각("6","27","월")은
        # 반드시 사라져야 한다. 매치 범위 밖의 "일"은 위 docstring 참조.
        leftover = [w[4] for w in words if w[4] in ("6", "27", "월")]
        self.assertEqual(
            leftover, [],
            f"매치 범위 안에 있던 옛 조각이 남아있다: {leftover} — "
            "일부 조각만 지워지고 새 텍스트와 겹쳤을 가능성이 높다",
        )

    def test_unrelated_same_line_occurrence_is_not_merged(self):
        """
        [안전] 같은 줄(Y좌표)에 있어도 멀리 떨어진(X간격 큰) 별개 발생은
        하나로 합쳐지면 안 된다 — 서로 다른 표 셀/컬럼의 같은 단어 등.
        """
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        # 같은 Y, 멀리 떨어진 X에 동일 문구 두 번 — 서로 다른 발생
        page.insert_text((72, 300), "개인정보", fontsize=11, fontname="korea-s", color=(0, 0, 0))
        page.insert_text((400, 300), "개인정보", fontsize=11, fontname="korea-s", color=(0, 0, 0))

        from apps.documents.patcher import _resolve_pdf_rect

        rect_result_1 = _resolve_pdf_rect(doc, {"type": "text_match", "occurrence": 1, "target_text": "개인정보"})
        rect_result_2 = _resolve_pdf_rect(doc, {"type": "text_match", "occurrence": 2, "target_text": "개인정보"})
        doc.close()

        self.assertIsNotNone(rect_result_1)
        self.assertIsNotNone(rect_result_2)
        # 두 발생의 rect가 서로 달라야 한다(하나로 합쳐지지 않았다는 뜻)
        self.assertNotEqual(rect_result_1[1], rect_result_2[1])
        # 각 rect의 폭이 좁아야 한다(두 발생이 하나의 넓은 박스로 합쳐지지 않았다는 뜻)
        self.assertLess(rect_result_1[1].width, 60)
        self.assertLess(rect_result_2[1].width, 60)


class PdfFailureTest(TestCase):
    """PDF 패처 실패 케이스 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_fail_user")
        self.pdf_bytes = _build_pdf_bytes("Hello World")
        self.upload = _make_upload(self.user, "fail.pdf", self.pdf_bytes, "pdf_fail_hash")
        self.version = _make_version(self.upload, self.user)

    def test_anchor_miss_sets_change_failed(self):
        """anchor 해석 실패(text_match 텍스트 없음) → change.status=failed."""
        change = _make_change(
            self.version,
            operation_id="op_fail_01",
            operation="annotate",
            anchor={
                "type": "text_match",
                "target_text": "존재하지 않는 텍스트",
                "page": 1,
            },
            replacement="무관",
        )
        patch_document_version(self.version.pk)

        change.refresh_from_db()
        self.assertEqual(
            change.status,
            DocumentChange.Status.FAILED,
            "anchor 해석 실패 시 change.status는 FAILED여야 한다",
        )

    def test_all_changes_failed_sets_version_failed(self):
        """모든 change 실패 → version.status=failed."""
        _make_change(
            self.version,
            operation_id="op_fail_02",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트A"},
        )
        _make_change(
            self.version,
            operation_id="op_fail_03",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트B"},
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "모든 change가 실패하면 version.status는 FAILED여야 한다",
        )

    def test_one_success_sets_version_ready(self):
        """하나라도 성공 → version.status=ready + artifact_file 생성."""
        # 실패할 change
        _make_change(
            self.version,
            operation_id="op_partial_01",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트"},
        )
        # 성공할 change (pdf_bbox — rect 값은 임의)
        _make_change(
            self.version,
            operation_id="op_partial_02",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
            },
            replacement="부분 성공 주석",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "하나라도 성공하면 version.status는 READY여야 한다",
        )

    def test_not_found_produces_no_artifact(self):
        """[AnchorResolver 연동] 해석 실패 시 renderer가 artifact를 만들지 않아야 한다."""
        from apps.documents.patcher import collect_applied_changes, render_pdf

        _make_change(
            self.version,
            operation_id="op_no_artifact",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "존재하지 않는 텍스트"},
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        patch_result = render_pdf(self.pdf_bytes, changes)

        self.assertEqual(patch_result.output_bytes, b"", "실패만 있으면 artifact bytes가 생성되면 안 된다")
        self.assertEqual(patch_result.applied_ids, [])


def _build_pdf_two_occurrences() -> bytes:
    """같은 Y좌표에 동일 문구 "개인정보"를 두 번 그린 PDF (occurrence 모호성 테스트용)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 300), "개인정보", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((400, 300), "개인정보", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class PdfAnchorAmbiguousTest(TestCase):
    """
    [앵커 해석 레이어] 후보가 여러 개인 text_match anchor는 자동 반영하지 않고
    NEEDS_CONFIRMATION으로 멈춰야 한다 (anchor_resolution.AnchorStatus.AMBIGUOUS).
    """

    def setUp(self):
        self.user = _make_user("pdf_ambiguous_user")
        self.pdf_bytes = _build_pdf_two_occurrences()
        self.upload = _make_upload(self.user, "ambiguous.pdf", self.pdf_bytes, "pdf_ambiguous_hash")
        self.version = _make_version(self.upload, self.user)

    def test_ambiguous_only_change_sets_needs_confirmation_not_applied(self):
        """occurrence 없이 후보 2개 → change/version 모두 NEEDS_CONFIRMATION, artifact 없음."""
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        change = _make_change(
            self.version,
            operation_id="op_ambiguous_01",
            operation="annotate",
            # occurrence 미지정 — 후보 2개라 AMBIGUOUS가 되어야 한다
            anchor={"type": "text_match", "target_text": "개인정보"},
            replacement="무관",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        patch_result = render_pdf(self.pdf_bytes, changes)

        self.assertEqual(patch_result.applied_ids, [])
        self.assertEqual(len(patch_result.needs_confirmation_items), 1)
        self.assertEqual(
            patch_result.needs_confirmation_items[0].get("code"),
            "ambiguous_anchor",
            "PDF 모호 항목에도 안정된 실패 사유 코드가 있어야 한다 (design v1 8절)",
        )
        self.assertEqual(patch_result.output_bytes, b"", "모호한 항목만 있으면 artifact가 생성되면 안 된다")

        persist_patch_result(self.version, patch_result, "pdf", changes)

        change.refresh_from_db()
        self.version.refresh_from_db()
        self.assertEqual(change.status, DocumentChange.Status.NEEDS_CONFIRMATION)
        self.assertEqual(self.version.status, DocumentVersion.Status.NEEDS_CONFIRMATION)
        self.assertFalse(self.version.artifact_file)
        # [코드리뷰 지적] version.status만 바뀌고 needs_confirmation_change_ids가 비어 있으면
        # 프론트(WorkspaceCenter)가 어떤 change가 확인이 필요한지 알 수 없다 — applied_change_ids와
        # 동일하게 이 경로에서도 채워져야 한다.
        self.assertEqual(self.version.needs_confirmation_change_ids, ["op_ambiguous_01"])

    def test_ambiguous_change_alongside_resolved_change_is_not_silently_applied(self):
        """모호한 항목 + 해석 가능한 항목이 섞이면, 모호한 항목은 반영되지 않고 NEEDS_CONFIRMATION으로 남아야 한다."""
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pdf

        ambiguous_change = _make_change(
            self.version,
            operation_id="op_mixed_ambiguous",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "개인정보"},
            replacement="무관",
        )
        resolved_change = _make_change(
            self.version,
            operation_id="op_mixed_resolved",
            operation="annotate",
            anchor={"type": "pdf_bbox", "page": 1, "rect": {"x0": 10, "y0": 10, "x1": 50, "y1": 30}},
            replacement="정상 반영",
        )
        changes = collect_applied_changes(self.version, operations=["annotate", "redact_overlay"])
        patch_result = render_pdf(self.pdf_bytes, changes)
        persist_patch_result(self.version, patch_result, "pdf", changes)

        ambiguous_change.refresh_from_db()
        resolved_change.refresh_from_db()
        self.version.refresh_from_db()

        self.assertEqual(resolved_change.status, DocumentChange.Status.APPLIED)
        self.assertEqual(ambiguous_change.status, DocumentChange.Status.NEEDS_CONFIRMATION)
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)
        self.assertIn("op_mixed_ambiguous", self.version.needs_confirmation_change_ids)
        self.assertNotIn("op_mixed_ambiguous", self.version.applied_change_ids)


def _build_pdf_two_pages() -> bytes:
    """텍스트가 있는 2페이지 PDF (페이지 수·빈 페이지 invariant 테스트용)."""
    import fitz

    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((72, 100), "접수번호", fontsize=12, fontname="korea-s", color=(0, 0, 0))
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 100), "담당자명", fontsize=12, fontname="korea-s", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _redact_without_insert(page, rect, change) -> None:
    """
    replacement 삽입 없이 redaction만 수행하는 가짜 apply — "검게 칠했는데
    아무것도 안 들어간" 버그 클래스(PR #29 계열)를 재현한다.
    """
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()


def _insert_without_redact(page, rect, change) -> None:
    """redaction 없이 replacement만 겹쳐 그리는 가짜 apply — original 잔존 케이스 재현."""
    page.insert_font(fontname="NotoSansKR", fontfile=str(
        __import__("pathlib").Path(__file__).resolve().parent / "fonts" / "NotoSansKR-Regular.ttf"
    ))
    page.insert_text((rect.x0, rect.y1 - 2), change.replacement, fontsize=11,
                     fontname="NotoSansKR", color=(0, 0, 0))


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfRenderValidationTest(TestCase):
    """
    [render 검증] design v1 7.1절 invariant 1~2 smoke check 테스트.

    patch가 적용됐다고 보고돼도 실제 렌더 결과에서 replacement가 추출되지 않거나
    original이 그 자리에 남아 있거나 문서 구조가 깨졌으면(페이지 수 변화·빈 페이지),
    artifact를 READY로 내보내지 않고 code=render_validation_failed로 멈춰야 한다.
    """

    def setUp(self):
        self.user = _make_user("pdf_validation_user")
        self.pdf_bytes = _build_pdf_bytes_cjk("접수번호")
        self.upload = _make_upload(self.user, "validate.pdf", self.pdf_bytes, "pdf_validation_hash")
        self.version = _make_version(self.upload, self.user)

    def _make_replace_change(self, operation_id="op_pdf_val_01", replacement="접수완료"):
        return _make_change(
            self.version,
            operation_id=operation_id,
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "접수번호", "page": 1, "occurrence": 1},
            original="접수번호",
            replacement=replacement,
        )

    def _render(self, original_bytes=None):
        from apps.documents.patcher import collect_applied_changes, render_pdf

        changes = collect_applied_changes(
            self.version, operations=["annotate", "redact_overlay", "replace_text"],
        )
        return render_pdf(original_bytes or self.pdf_bytes, changes), changes

    def test_invisible_replacement_fails_validation_with_code(self):
        """[invariant 1] replacement가 추출되지 않으면 artifact 없이 render_validation_failed."""
        self._make_replace_change()
        with mock_patch("apps.documents.patcher._apply_pdf_redact_overlay", side_effect=_redact_without_insert):
            result, _ = self._render()

        self.assertEqual(result.applied_ids, [], "검증 실패 항목이 applied로 보고되면 안 된다")
        self.assertEqual(result.output_bytes, b"", "검증 실패 시 artifact bytes가 생성되면 안 된다")
        self.assertEqual(len(result.failed_items), 1)
        item = result.failed_items[0]
        self.assertEqual(item["operation_id"], "op_pdf_val_01")
        self.assertEqual(item.get("code"), "render_validation_failed")
        self.assertIn("추출되지 않음", item["reason"])

    def test_leftover_original_fails_validation(self):
        """[invariant 1] redaction 누락으로 original이 rect 자리에 남으면 검증 실패."""
        self._make_replace_change()
        with mock_patch("apps.documents.patcher._apply_pdf_redact_overlay", side_effect=_insert_without_redact):
            result, _ = self._render()

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.output_bytes, b"")
        self.assertEqual(len(result.failed_items), 1)
        item = result.failed_items[0]
        self.assertEqual(item.get("code"), "render_validation_failed")
        self.assertIn("남아 있음", item["reason"])

    def test_page_count_change_fails_validation(self):
        """[invariant 2] 수정본 페이지 수가 원본과 다르면 검증 실패."""
        self.pdf_bytes = _build_pdf_two_pages()

        def _delete_second_page(page, rect, change):
            page.parent.delete_page(1)

        self._make_replace_change(operation_id="op_pdf_val_pages")
        with mock_patch("apps.documents.patcher._apply_pdf_redact_overlay", side_effect=_delete_second_page):
            result, _ = self._render()

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.output_bytes, b"")
        self.assertEqual(len(result.failed_items), 1)
        item = result.failed_items[0]
        self.assertEqual(item.get("code"), "render_validation_failed")
        self.assertIn("페이지 수", item["reason"])

    def test_unexpected_empty_page_fails_validation(self):
        """[invariant 2] 원래 텍스트가 있던 페이지가 수정 후 비면 검증 실패."""
        self.pdf_bytes = _build_pdf_two_pages()

        def _nuke_second_page(page, rect, change):
            # annotate 자체는 수행하지 않고, 대상이 아닌 2페이지의 텍스트를 전부 지운다
            other = page.parent[1]
            other.add_redact_annot(other.rect, fill=(1, 1, 1))
            other.apply_redactions()

        _make_change(
            self.version,
            operation_id="op_pdf_val_empty",
            operation="annotate",
            anchor={"type": "pdf_bbox", "page": 1, "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104}},
            replacement="검토 필요",
        )
        with mock_patch("apps.documents.patcher._apply_pdf_annotate", side_effect=_nuke_second_page):
            result, _ = self._render()

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.output_bytes, b"")
        self.assertEqual(len(result.failed_items), 1)
        item = result.failed_items[0]
        self.assertEqual(item.get("code"), "render_validation_failed")
        self.assertIn("비어 있음", item["reason"])

    def test_empty_replacement_redact_passes_validation(self):
        """[경계] replacement가 빈 문자열인 삭제형 redact는 페이지가 비어도 통과해야 한다."""
        self._make_replace_change(operation_id="op_pdf_val_delete", replacement="")
        result, _ = self._render()

        self.assertEqual(result.applied_ids, ["op_pdf_val_delete"])
        self.assertEqual(result.failed_items, [])
        self.assertGreater(len(result.output_bytes), 0, "삭제형 redact는 artifact가 생성되어야 한다")

    def test_mixed_valid_and_invisible_changes_produce_no_artifact(self):
        """검증 실패가 하나라도 있으면 정상 항목까지 포함해 artifact를 내보내지 않는다."""
        import fitz
        from apps.documents import patcher

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "접수번호", fontsize=12, fontname="korea-s", color=(0, 0, 0))
        page.insert_text((72, 200), "담당자명", fontsize=12, fontname="korea-s", color=(0, 0, 0))
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        self.pdf_bytes = buf.getvalue()

        self._make_replace_change(operation_id="op_pdf_val_good")
        _make_change(
            self.version,
            operation_id="op_pdf_val_bad",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "담당자명", "page": 1, "occurrence": 1},
            original="담당자명",
            replacement="홍길동",
        )

        real_apply = patcher._apply_pdf_redact_overlay

        def _selective(page, rect, change):
            if change.operation_id == "op_pdf_val_bad":
                _redact_without_insert(page, rect, change)
                return
            real_apply(page, rect, change)

        with mock_patch("apps.documents.patcher._apply_pdf_redact_overlay", side_effect=_selective):
            result, _ = self._render()

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.output_bytes, b"", "부분 검증 실패여도 artifact를 내보내면 안 된다")
        failed_by_id = {item["operation_id"]: item for item in result.failed_items}
        self.assertEqual(set(failed_by_id), {"op_pdf_val_good", "op_pdf_val_bad"})
        self.assertEqual(failed_by_id["op_pdf_val_bad"].get("code"), "render_validation_failed")
        self.assertEqual(failed_by_id["op_pdf_val_good"].get("code"), "render_validation_failed")
        self.assertIn("추출되지 않음", failed_by_id["op_pdf_val_bad"]["reason"])
        self.assertIn("함께 중단", failed_by_id["op_pdf_val_good"]["reason"])

    def test_validation_failure_via_task_sets_version_failed(self):
        """task 경로: 검증 실패 → version FAILED, change FAILED, artifact 없음."""
        change = self._make_replace_change(operation_id="op_pdf_val_task")
        with mock_patch("apps.documents.patcher._apply_pdf_redact_overlay", side_effect=_redact_without_insert):
            patch_document_version(self.version.pk)

        change.refresh_from_db()
        self.version.refresh_from_db()
        self.assertEqual(change.status, DocumentChange.Status.FAILED)
        self.assertEqual(self.version.status, DocumentVersion.Status.FAILED)
        self.assertFalse(self.version.artifact_file, "검증 실패 시 artifact가 저장되면 안 된다")
        self.assertIn("render 검증 실패", self.version.error_message)
