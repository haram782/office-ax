from pathlib import PurePosixPath
from urllib.parse import quote, unquote

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from apps.chat.models import ChatMessage
from apps.documents.models import DocumentVersion, UploadLog
from apps.rag.models import RagAsset


def _safe_storage_name(raw_path: str) -> str | None:
    name = unquote(raw_path or "")
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or "//" in name
        or "\\" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path.as_posix()


def _owns_upload(user, name: str) -> bool:
    return UploadLog.objects.filter(user=user, file=name).exists()


def _owns_artifact(user, name: str) -> bool:
    if DocumentVersion.objects.filter(upload_log__user=user, artifact_file=name).exists():
        return True
    url = f"/media/{name}"
    if ChatMessage.objects.filter(session__user=user, artifact_url=url).exists():
        return True
    # 레거시 result JSON은 사용자 범위의 행만 검사해 전체 테이블 순회를 피한다.
    for result in UploadLog.objects.filter(user=user, result__isnull=False).values_list("result", flat=True):
        if isinstance(result, dict) and result.get("artifact_url") == url:
            return True
    return False


def _owns_render(user, name: str, namespace: str) -> bool:
    parts = name.split("/")
    if len(parts) < 3 or parts[0] != namespace or not parts[1].isdigit():
        return False
    return UploadLog.objects.filter(pk=int(parts[1]), user=user).exists()


def _owns_rag(user, name: str) -> bool:
    return RagAsset.objects.filter(owner=user, file=name).exists()


_RESOLVERS = {
    "uploads": _owns_upload,
    "artifacts": _owns_artifact,
    "slides": lambda user, name: _owns_render(user, name, "slides"),
    "docx_pdf": lambda user, name: _owns_render(user, name, "docx_pdf"),
    "rag_assets": _owns_rag,
}


@require_http_methods(["GET", "HEAD"])
def protected_media(request, path: str):
    name = _safe_storage_name(path)
    namespace = name.split("/", 1)[0] if name else ""
    resolver = _RESOLVERS.get(namespace)
    if not request.user.is_authenticated or resolver is None or not resolver(request.user, name):
        raise Http404

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/_protected_media/{quote(name, safe='/')}"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
