import tempfile
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.chat.models import ChatMessage, ChatSession
from apps.documents.models import DocumentVersion, FileStructure, UploadLog
from apps.rag.models import RagAsset


User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MediaGatewayTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        structure = FileStructure.objects.create(hash="a" * 32, source_type="pdf")
        self.upload = UploadLog.objects.create(
            user=self.owner,
            file_structure=structure,
            original_filename="보고서.pdf",
            status=UploadLog.Status.DONE,
        )
        self.upload.file.save("보고서.pdf", ContentFile(b"pdf"), save=True)
        self.version = DocumentVersion.objects.create(
            upload_log=self.upload,
            version_number=1,
            status=DocumentVersion.Status.READY,
            created_by=self.owner,
        )
        self.version.artifact_file.save("result.pdf", ContentFile(b"artifact"), save=True)
        self.rag = RagAsset.objects.create(
            kind=RagAsset.Kind.TONE,
            group_name="tone",
            file=ContentFile(b"rag", name="tone.txt"),
            file_size=3,
            owner=self.owner,
        )
        self.session = ChatSession.objects.create(user=self.owner)
        self.chat_message = ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            artifact_url="/media/artifacts/chat-only-result.pdf",
        )
        from django.core.files.storage import default_storage

        default_storage.save("artifacts/chat-only-result.pdf", ContentFile(b"chat-artifact"))
        self.legacy_result_upload = UploadLog.objects.create(
            user=self.owner,
            file_structure=structure,
            original_filename="legacy.pdf",
            status=UploadLog.Status.DONE,
            result={"artifact_url": "/media/artifacts/legacy-result.pdf"},
        )
        default_storage.save("artifacts/legacy-result.pdf", ContentFile(b"legacy-artifact"))
        self.client.force_login(self.owner)

    def assert_allowed(self, path):
        response = self.client.get(f"/media/{path}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], f"/_protected_media/{quote(path, safe='/')}")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_owner_exact_upload_artifact_render_and_rag_are_allowed(self):
        self.assert_allowed(self.upload.file.name)
        self.assert_allowed(self.version.artifact_file.name)
        self.assert_allowed(f"slides/{self.upload.pk}/slide_1.png")
        self.assert_allowed(f"docx_pdf/{self.upload.pk}/page_1.png")
        self.assert_allowed(self.rag.file.name)

    def test_head_and_query_string_preserve_url_contract(self):
        response = self.client.head(f"/media/{self.upload.file.name}?v=123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], f"/_protected_media/{quote(self.upload.file.name, safe='/')}")

    def test_pdf_response_content_type_is_pdf_not_default_html(self):
        response = self.client.get(f"/media/{self.upload.file.name}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_image_render_content_type_is_png(self):
        response = self.client.get(f"/media/slides/{self.upload.pk}/slide_1.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_unknown_extension_falls_back_to_octet_stream(self):
        self.upload.file.save("data.bin", ContentFile(b"bin"), save=True)
        response = self.client.get(f"/media/{self.upload.file.name}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")

    def test_unauthenticated_and_other_owner_are_non_enumerating_404(self):
        path = self.upload.file.name
        self.client.logout()
        self.assertEqual(self.client.get(f"/media/{path}").status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/media/{path}").status_code, 404)

    def test_unknown_and_traversal_paths_fail_closed(self):
        for path in ("unknown/file.pdf", "../secret", "uploads\\secret", "uploads//secret", "/etc/passwd", ""):
            self.assertEqual(self.client.get(f"/media/{path}").status_code, 404)

    def test_rag_owner_id_in_path_is_not_trusted(self):
        forged = self.rag.file.name.replace(f"/{self.owner.pk}/", f"/{self.other.pk}/")
        self.assertEqual(self.client.get(f"/media/{forged}").status_code, 404)

    def test_write_methods_are_rejected_regardless_of_ownership(self):
        path = self.upload.file.name
        for verb in ("post", "put", "patch", "delete", "options"):
            response = getattr(self.client, verb)(f"/media/{path}")
            self.assertEqual(response.status_code, 405, verb)
            self.assertNotIn("X-Accel-Redirect", response)

    def test_other_owner_cannot_reach_document_version_artifact(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/media/{self.version.artifact_file.name}").status_code, 404)

    def test_other_owner_cannot_reach_chat_message_artifact(self):
        self.assert_allowed("artifacts/chat-only-result.pdf")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/media/artifacts/chat-only-result.pdf").status_code, 404)

    def test_other_owner_cannot_reach_legacy_upload_result_artifact(self):
        self.assert_allowed("artifacts/legacy-result.pdf")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/media/artifacts/legacy-result.pdf").status_code, 404)

    def test_other_owner_cannot_reach_slides_render(self):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/media/slides/{self.upload.pk}/slide_1.png").status_code, 404
        )

    def test_other_owner_cannot_reach_docx_pdf_render(self):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/media/docx_pdf/{self.upload.pk}/page_1.png").status_code, 404
        )

    def test_other_owner_cannot_reach_exact_rag_file(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/media/{self.rag.file.name}").status_code, 404)
