import tempfile
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

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
