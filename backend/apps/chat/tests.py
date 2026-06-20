"""
doc-viewer-remediation 변경 회귀 테스트 + document-change-highlighting 백엔드 테스트.

검증 대상:
  1. notify_chat_response(async 경로): assistant ChatMessage.upload_log_id == user upload_log_id
  2. ChatMessageCreateView duplicate 경로: assistant ChatMessage.upload_log_id == dup_upload_log_id
  3. notify_chat_response: change_highlights 전달 및 corrections 파생 검증
  4. PptxPatchView: text 패치에 대해 change_highlights 반환 검증
  5. PptxPatchView: table_cell 패치에 대해 change_highlights 반환 검증
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.models import FileStructure, UploadLog
from apps.chat.models import ChatMessage, ChatSession
from apps.chat.tasks import notify_chat_response

User = get_user_model()


# ── 공통 픽스처 헬퍼 ────────────────────────────────────────────────────────────

def _make_user(username="tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_session(user):
    return ChatSession.objects.create(user=user, title="테스트 세션")


def _make_upload_log(user, filename="test.xlsx", status=UploadLog.Status.PENDING):
    fs, _ = FileStructure.objects.get_or_create(
        hash="abc123",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
        status=status,
        file_hash="deadbeef",
    )


def _make_user_message(session, upload_log):
    return ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content="",
        upload_log=upload_log,
    )


# ── 1. notify_chat_response: async 완료 경로 ────────────────────────────────────

class NotifyChatResponseUploadLogTest(TestCase):
    """
    정상 async 완료 경로에서 생성된 assistant ChatMessage가
    user 메시지의 upload_log를 그대로 참조하는지 검증.
    """

    def setUp(self):
        self.user = _make_user()
        self.session = _make_session(self.user)
        self.upload_log = _make_upload_log(self.user)
        self.user_msg = _make_user_message(self.session, self.upload_log)

    def test_assistant_message_upload_log_matches_user_upload_log(self):
        # given: 분석 완료 결과
        result = {
            "summary": "분석 완료",
            "source_type": "excel",
            "artifact_url": "/media/corrected.xlsx",
            "snippet_data": {},
            "errors": [],
        }

        # when: Celery task 콜백 실행
        notify_chat_response(self.user_msg.pk, result)

        # then: assistant 메시지의 upload_log_id가 user 업로드와 동일
        assistant = ChatMessage.objects.get(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        )
        self.assertEqual(
            assistant.upload_log_id,
            self.upload_log.pk,
            "async 완료 경로: assistant.upload_log_id가 user upload_log_id와 일치해야 함",
        )

    def test_upload_log_status_set_to_done(self):
        # upload_log.status가 DONE으로 갱신되는지도 함께 확인
        result = {"summary": "완료", "source_type": "excel"}
        notify_chat_response(self.user_msg.pk, result)

        self.upload_log.refresh_from_db()
        self.assertEqual(self.upload_log.status, UploadLog.Status.DONE)


# ── 2. duplicate 경로: views.py ─────────────────────────────────────────────────

class DuplicateUploadAssistantBindingTest(TestCase):
    """
    동일 파일 재업로드(중복) 경로에서 생성된 assistant ChatMessage가
    신규로 생성된 dup_upload_log를 참조하는지 검증.
    """

    def setUp(self):
        self.user = _make_user(username="dup_tester")
        self.session = _make_session(self.user)

        # 기존에 완료된 UploadLog (원본)
        fs, _ = FileStructure.objects.get_or_create(
            hash="dup_hash_001",
            defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
        )
        self.existing_log = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="original.xlsx",
            status=UploadLog.Status.DONE,
            file_hash="sha256same",
            result={
                "summary": "기존 결과",
                "source_type": "excel",
                "artifact_url": "/media/original.xlsx",
                "snippet_data": {},
            },
        )

    def test_duplicate_assistant_message_uses_new_upload_log(self):
        """
        duplicate 분기에서 생성하는 dup_upload_log의 id가
        assistant ChatMessage.upload_log_id로 저장되어야 한다.
        """
        from rest_framework.test import APIClient

        client = APIClient()
        # force_authenticate: 토큰/세션 없이 인증 통과
        client.force_authenticate(user=self.user)

        # 동일 SHA-256 파일을 다시 업로드하는 상황을 시뮬레이션
        with patch("apps.chat.views.compute_sha256", return_value="sha256same"), \
             patch("apps.chat.views.default_storage.save", return_value="uploads/dup.xlsx"), \
             patch("apps.chat.views.default_storage.delete"), \
             patch("apps.chat.views.os.path.join", return_value="/tmp/dup.xlsx"), \
             patch("apps.chat.views.extract_excel_columns", return_value=[]):

            file_data = SimpleUploadedFile("dup.xlsx", b"fake", content_type="application/vnd.ms-excel")
            response = client.post(
                f"/api/v1/chat/sessions/{self.session.pk}/messages/send/",
                {"file": file_data},
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "duplicate")

        # 생성된 dup_upload_log 찾기 (기존 log와 다른 새 레코드)
        dup_log = UploadLog.objects.exclude(pk=self.existing_log.pk).filter(
            user=self.user, file_hash="sha256same"
        ).first()
        self.assertIsNotNone(dup_log, "dup_upload_log가 생성되어야 함")

        # assistant 메시지가 dup_log를 참조하는지 확인
        assistant = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).first()
        self.assertIsNotNone(assistant)
        self.assertEqual(
            assistant.upload_log_id,
            dup_log.pk,
            "duplicate 경로: assistant.upload_log_id가 새 dup_upload_log.id와 일치해야 함",
        )


# ── 3. UploadLogSerializer: file_hash 노출 검증 ─────────────────────────────────

class UploadLogSerializerFileHashTest(TestCase):
    """
    UploadLogSerializer가 file_hash 필드를 직렬화 결과에 포함하는지 검증.
    프론트엔드가 file_hash 기준으로 중복 파일을 필터링하기 위해 필요하다.
    """

    def test_file_hash_in_serialized_output(self):
        user = _make_user(username="hash_tester")
        log = _make_upload_log(user)

        from apps.documents.serializers import UploadLogSerializer
        data = UploadLogSerializer(log).data

        self.assertIn("file_hash", data, "UploadLogSerializer 결과에 file_hash가 포함되어야 함")
        self.assertEqual(data["file_hash"], "deadbeef")


# ── 4. change_highlights 전달 및 corrections 파생 ────────────────────────────────

class NotifyChatResponseChangeHighlightsTest(TestCase):
    """
    notify_chat_response가 change_highlights를 snippet_data에 올바르게 포함하는지 검증.
    - result에 직접 change_highlights가 있으면 그대로 전달
    - snippet_data.corrections 가 있으면 change_highlights 로 파생
    """

    def setUp(self):
        self.user = _make_user(username="hl_tester")
        self.session = _make_session(self.user)
        self.upload_log = _make_upload_log(self.user)
        self.user_msg = _make_user_message(self.session, self.upload_log)

    def test_explicit_change_highlights_preserved_in_snippet_data(self):
        """result에 포함된 change_highlights 가 snippet_data 에 그대로 저장되어야 한다."""
        highlights = [{"id": "hl-0", "kind": "correction", "cell": "A1"}]
        result = {
            "summary": "완료",
            "source_type": "excel",
            "artifact_url": "/media/out.xlsx",
            "snippet_data": {
                "type": "excel_preview",
                "headers": [],
                "preview_rows": [],
                "corrections": [],
                "change_highlights": highlights,
            },
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant = ChatMessage.objects.get(
            session=self.session, role=ChatMessage.Role.ASSISTANT
        )
        self.assertIn("change_highlights", assistant.snippet_data)
        self.assertEqual(assistant.snippet_data["change_highlights"], highlights)

    def test_corrections_derived_into_change_highlights(self):
        """snippet_data.corrections 가 있으면 change_highlights 로 자동 파생되어야 한다."""
        corrections = [
            {"cell": "D12", "original": "-15,000", "corrected": "15,000"},
            {"cell": "D27", "original": "-3,200",  "corrected": "3,200"},
        ]
        result = {
            "summary": "완료",
            "source_type": "excel",
            "artifact_url": "/media/out.xlsx",
            "snippet_data": {
                "type":         "excel_preview",
                "headers":      [],
                "preview_rows": [],
                "corrections":  corrections,
            },
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant = ChatMessage.objects.get(
            session=self.session, role=ChatMessage.Role.ASSISTANT
        )
        highlights = assistant.snippet_data.get("change_highlights", [])
        self.assertEqual(len(highlights), 2, "corrections 2건이 highlights 2건으로 파생되어야 함")
        self.assertEqual(highlights[0]["cell"], "D12")
        self.assertEqual(highlights[0]["kind"], "correction")
        self.assertEqual(highlights[0]["target"], "cell")
        self.assertEqual(highlights[1]["cell"], "D27")

    def test_fallback_demo_corrections_derived_into_change_highlights(self):
        """result.snippet_data 없는 fallback 경로에서도 corrections -> change_highlights 파생."""
        result = {
            "summary": "완료",
            "source_type": "excel",
            "artifact_url": "/media/out.xlsx",
            # snippet_data 없음 → tasks.py fallback 데이터 사용
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant = ChatMessage.objects.get(
            session=self.session, role=ChatMessage.Role.ASSISTANT
        )
        highlights = assistant.snippet_data.get("change_highlights", [])
        # fallback corrections 4건
        self.assertGreater(len(highlights), 0, "fallback corrections에서 highlights 파생 필요")
        self.assertEqual(highlights[0]["kind"], "correction")

    def test_pptx_result_change_highlights_passed_through(self):
        """PPTX 분석 결과의 change_highlights 가 snippet_data 에 포함되어야 한다."""
        pptx_highlights = [
            {"id": "pptx-0", "kind": "analysis", "slide_index": 0, "target": "slide"}
        ]
        result = {
            "summary": "PPTX 분석 완료",
            "source_type": "pptx",
            "slide_urls": ["/media/slides/1/slide_1.png"],
            "change_highlights": pptx_highlights,
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant = ChatMessage.objects.get(
            session=self.session, role=ChatMessage.Role.ASSISTANT
        )
        self.assertIn("change_highlights", assistant.snippet_data)
        self.assertEqual(assistant.snippet_data["change_highlights"], pptx_highlights)


# ── 4 & 5. PptxPatchView change_highlights 반환 ─────────────────────────────────

class PptxPatchViewChangeHighlightsTest(TestCase):
    """
    PptxPatchView POST 응답에 change_highlights 가 포함되어야 한다.
    - text 패치: slide_index, shape_index 포함
    - table_cell 패치: slide_index, shape_index, row_index, col_index 포함
    LibreOffice/python-pptx 의존 없이 mock으로 검증.
    """

    def setUp(self):
        self.user = _make_user(username="patch_tester")
        self.session = _make_session(self.user)

        fs, _ = FileStructure.objects.get_or_create(
            hash="pptx_hash_001",
            defaults={"source_type": FileStructure.SourceType.PPTX, "column_schema": []},
        )
        self.upload_log = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="test.pptx",
            status=UploadLog.Status.DONE,
            file_hash="pptxhash",
            file="uploads/test.pptx",
        )

    def _post_patch(self, patches):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client.post(
            "/api/v1/chat/pptx-patch/",
            {"upload_log_id": self.upload_log.pk, "patches": patches},
            format="json",
        )

    def test_text_patch_returns_change_highlights(self):
        """text 패치 후 change_highlights 에 slide_index, shape_index 가 포함되어야 한다."""
        patches = [{"slide_index": 1, "shape_index": 0, "type": "text", "new_text": "수정 제목"}]

        # python-pptx 와 render_one_slide 모킹
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_para = MagicMock()
        mock_para.text = "원본 제목"
        mock_para.runs = [MagicMock()]
        mock_shape.text_frame.paragraphs = [mock_para]

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [MagicMock(), mock_slide]  # slide_index=1

        with patch("apps.chat.views.Presentation", return_value=mock_prs), \
             patch("apps.chat.views.render_one_slide", return_value="/media/slides/1/slide_2.png"), \
             patch("apps.chat.views.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: MagicMock()
            response = self._post_patch(patches)

        self.assertEqual(response.status_code, 200)
        self.assertIn("change_highlights", response.data)
        highlights = response.data["change_highlights"]
        self.assertEqual(len(highlights), 1)
        self.assertEqual(highlights[0]["slide_index"], 1)
        self.assertEqual(highlights[0]["shape_index"], 0)
        self.assertEqual(highlights[0]["kind"], "patch")
        self.assertEqual(highlights[0]["format"], "pptx")
        self.assertEqual(highlights[0]["corrected"], "수정 제목")

    def test_table_cell_patch_returns_change_highlights_with_row_col(self):
        """table_cell 패치 후 row_index, col_index 가 change_highlights 에 포함되어야 한다."""
        patches = [
            {"slide_index": 0, "shape_index": 1, "type": "table_cell",
             "row_index": 2, "col_index": 3, "new_text": "변경값"}
        ]

        mock_cell = MagicMock()
        mock_cell_tf = MagicMock()
        mock_cell_para = MagicMock()
        mock_cell_para.text = "원본값"
        mock_cell_tf.paragraphs = [mock_cell_para]
        mock_cell.text_frame = mock_cell_tf

        mock_row = MagicMock()
        mock_row.cells = [MagicMock(), MagicMock(), MagicMock(), mock_cell]

        mock_table = MagicMock()
        mock_table.rows = [MagicMock(), MagicMock(), mock_row]

        mock_shape = MagicMock()
        mock_shape.has_text_frame = False
        mock_shape.has_table = True
        mock_shape.table = mock_table

        mock_slide = MagicMock()
        mock_slide.shapes = [MagicMock(), mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        with patch("apps.chat.views.Presentation", return_value=mock_prs), \
             patch("apps.chat.views.render_one_slide", return_value="/media/slides/1/slide_1.png"), \
             patch("apps.chat.views.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: MagicMock()
            response = self._post_patch(patches)

        self.assertEqual(response.status_code, 200)
        self.assertIn("change_highlights", response.data)
        highlights = response.data["change_highlights"]
        self.assertEqual(len(highlights), 1)
        self.assertEqual(highlights[0]["target"], "table_cell")
        self.assertEqual(highlights[0]["row_index"], 2)
        self.assertEqual(highlights[0]["col_index"], 3)
        self.assertEqual(highlights[0]["slide_index"], 0)
        self.assertEqual(highlights[0]["shape_index"], 1)
