from pathlib import PurePosixPath
from urllib.parse import quote, unquote

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from apps.chat.models import ChatMessage
from apps.documents.models import DocumentVersion, UploadLog
from apps.rag.models import RagAsset

# X-Accel-Redirect internal redirect는 Django 응답의 Content-Type을 그대로 보존하므로
# 여기서 명시하지 않으면 HttpResponse 기본값인 text/html이 그대로 브라우저에 전달된다.
# 확장자 기반 allowlist만 사용해 요청 경로 문자열을 그대로 헤더에 반영하지 않는다.
# SVG는 인라인 <script>/이벤트 핸들러를 담을 수 있는 active content라 same-origin으로
# image/svg+xml을 부여하면 저장된 XSS가 가능해진다. allowlist에서 제외해
# application/octet-stream fallback으로 강제 다운로드/비활성 콘텐츠로 취급한다.
_SAFE_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".hwp": "application/x-hwp",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_DEFAULT_CONTENT_TYPE = "application/octet-stream"


def _safe_content_type(name: str) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    return _SAFE_CONTENT_TYPES.get(suffix, _DEFAULT_CONTENT_TYPE)


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

    response = HttpResponse(content_type=_safe_content_type(name))
    response["X-Accel-Redirect"] = f"/_protected_media/{quote(name, safe='/')}"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
