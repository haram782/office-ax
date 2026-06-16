import logging
import os
import uuid
from pathlib import Path

from celery import current_app
from django.conf import settings
from django.core.files.storage import default_storage
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import FileStructure, UploadLog, compute_file_structure_hash, pdf_structure_hash
from apps.documents.utils import compute_sha256, extract_excel_columns, extract_csv_columns, generic_structure_hash
from .models import ChatSession, ChatMessage, UserActionLog
from .serializers import (
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    ChatSessionCreateSerializer,
    ChatSessionSerializer,
)

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc", ".pptx", ".hwp", ".hwpx", ".png", ".jpg", ".jpeg", ".webp", ".gif"}

# suffix → FileStructure.SourceType
_SUFFIX_TO_SOURCE_TYPE = {
    ".xlsx": FileStructure.SourceType.EXCEL,
    ".xls":  FileStructure.SourceType.EXCEL,
    ".csv":  FileStructure.SourceType.CSV,
    ".pdf":  FileStructure.SourceType.PDF,
    ".docx": FileStructure.SourceType.DOCX,
    ".doc":  FileStructure.SourceType.DOCX,
    ".pptx": FileStructure.SourceType.PPTX,
    ".hwp":  FileStructure.SourceType.HWP,
    ".hwpx": FileStructure.SourceType.HWP,
    ".png":  FileStructure.SourceType.IMAGE,
    ".jpg":  FileStructure.SourceType.IMAGE,
    ".jpeg": FileStructure.SourceType.IMAGE,
    ".webp": FileStructure.SourceType.IMAGE,
    ".gif":  FileStructure.SourceType.IMAGE,
}

# suffix → UserActionLog.FileType
_SUFFIX_TO_FILE_TYPE = {
    ".xlsx": UserActionLog.FileType.EXCEL,
    ".xls":  UserActionLog.FileType.EXCEL,
    ".csv":  UserActionLog.FileType.CSV,
    ".pdf":  UserActionLog.FileType.PDF_DIGITAL,
    ".docx": UserActionLog.FileType.DOCX,
    ".doc":  UserActionLog.FileType.DOCX,
    ".pptx": UserActionLog.FileType.PPTX,
    ".hwp":  UserActionLog.FileType.HWP,
    ".hwpx": UserActionLog.FileType.HWP,
    ".png":  UserActionLog.FileType.IMAGE,
    ".jpg":  UserActionLog.FileType.IMAGE,
    ".jpeg": UserActionLog.FileType.IMAGE,
    ".webp": UserActionLog.FileType.IMAGE,
    ".gif":  UserActionLog.FileType.IMAGE,
}


class ChatSessionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ChatSessionSerializer(many=True)})
    def get(self, request):
        sessions = ChatSession.objects.filter(user=request.user).prefetch_related("messages")
        return Response(ChatSessionSerializer(sessions, many=True).data)

    @extend_schema(
        request=ChatSessionCreateSerializer,
        responses={201: ChatSessionCreateSerializer},
    )
    def post(self, request):
        serializer = ChatSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = ChatSession.objects.create(
            user=request.user,
            title=serializer.validated_data.get("title", ""),
        )
        return Response(ChatSessionCreateSerializer(session).data, status=status.HTTP_201_CREATED)


class ChatMessageListView(ListAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ChatMessage.objects
            .filter(session_id=self.kwargs["session_id"], session__user=self.request.user)
            .select_related("upload_log")
        )


class ChatMessageCreateView(APIView):
    parser_classes = [MultiPartParser, JSONParser]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="채팅 메시지 전송 (파일 첨부 가능)",
        description=(
            "텍스트만 보내거나 파일을 첨부할 수 있습니다. "
            "파일 첨부 시 SHA-256 해시로 중복 검사 후 AI 분석이 비동기로 시작됩니다."
        ),
        request=ChatMessageCreateSerializer,
        responses={
            202: OpenApiResponse(description="접수 완료 (비동기 처리 중 또는 중복으로 즉시 반환)"),
            400: OpenApiResponse(description="content/file 중 하나 필수, 또는 미지원 형식"),
            404: OpenApiResponse(description="세션 없음"),
        },
    )
    def post(self, request, session_id: int):
        try:
            session = ChatSession.objects.get(pk=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = serializer.validated_data.get("content", "")
        file = serializer.validated_data.get("file")

        # 세션 제목 자동 설정
        if not session.title:
            session.title = (content or getattr(file, "name", "새 대화"))[:50]
            session.save(update_fields=["title"])

        user_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.USER,
            content=content,
        )

        # ── 텍스트 전용 메시지 ───────────────────────────────────────────────────
        if not file:
            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content="파일을 첨부하면 AI가 문서를 분석합니다.",
            )
            return Response(
                {"message_id": user_message.pk, "session_id": session.pk, "status": "sent"},
                status=status.HTTP_202_ACCEPTED,
            )

        # ── 파일 형식 검사 ───────────────────────────────────────────────────────
        suffix = Path(file.name).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            user_message.delete()
            return Response(
                {"error": f"지원 형식: {', '.join(_ALLOWED_SUFFIXES)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 파일 저장 → SHA-256 해시 계산 ───────────────────────────────────────
        storage_name = f"uploads/{uuid.uuid4().hex}_{file.name}"
        saved_rel = default_storage.save(storage_name, file)      # media/uploads/... (상대경로)
        abs_path = os.path.join(str(settings.MEDIA_ROOT), saved_rel)
        sha256 = compute_sha256(abs_path)

        # ── 중복 감지: 동일 파일을 이미 완료 처리한 기록이 있는 경우 ─────────────
        existing_log = UploadLog.objects.filter(
            user=request.user,
            file_hash=sha256,
            status=UploadLog.Status.DONE,
        ).first()

        if existing_log and existing_log.result:
            # 중복 파일 → 새 저장 파일 제거, 기존 결과 즉시 반환
            default_storage.delete(saved_rel)

            dup_upload_log = UploadLog.objects.create(
                user=request.user,
                file_structure=existing_log.file_structure,
                original_filename=file.name,
                status=UploadLog.Status.DONE,
                file_hash=sha256,
                result=existing_log.result,
                # 기존 파일 레퍼런스 재사용 (미리보기용)
                file=existing_log.file.name if existing_log.file else None,
            )

            user_message.upload_log = dup_upload_log
            user_message.save(update_fields=["upload_log"])

            result = existing_log.result
            summary = result.get("summary", "이전 분석 결과입니다.")
            errors = result.get("errors", [])
            artifact_url = result.get("artifact_url", "")

            lines = ["⚡ 이미 분석 완료된 동일한 문서입니다. 기존 결과를 즉시 표시합니다.\n", summary]
            if errors:
                lines.append(f"\n**감지된 오류 {len(errors)}건**")
                lines.extend(f"• {e}" for e in errors[:5])

            # 파일 타입별 snippet_data 구성
            dup_source_type   = result.get("source_type", "")
            dup_slide_urls    = result.get("slide_urls", [])
            dup_docx_page_urls = result.get("docx_page_urls", [])
            if dup_source_type == "pptx":
                dup_has_snippet  = bool(dup_slide_urls)
                dup_snippet_data = {
                    "type":             "pptx_preview",
                    "upload_log_id":    dup_upload_log.pk,
                    "slide_urls":       dup_slide_urls,
                    "slide_count":      len(dup_slide_urls),
                    "pptx_structured":  result.get("pptx_structured", []),
                    "render_available": bool(dup_slide_urls),
                }
            elif dup_source_type == "docx":
                dup_has_snippet  = bool(dup_docx_page_urls)
                dup_snippet_data = {
                    "type":             "docx_pages",
                    "page_urls":        dup_docx_page_urls,
                    "page_count":       len(dup_docx_page_urls),
                    "render_available": bool(dup_docx_page_urls),
                }
            else:
                dup_has_snippet  = bool(artifact_url)
                dup_snippet_data = result.get("snippet_data", {})

            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content="\n".join(lines),
                artifact_url=artifact_url,
                has_snippet=dup_has_snippet,
                snippet_data=dup_snippet_data,
            )

            # ── 중복 감지 행동 로그 ────────────────────────────────────────────
            _file_type = _SUFFIX_TO_FILE_TYPE.get(suffix, UserActionLog.FileType.UNKNOWN)
            UserActionLog.objects.create(
                user=request.user,
                session=session,
                upload_log=dup_upload_log,
                action_type=UserActionLog.ActionType.DUPLICATE_HIT,
                file_type=_file_type,
                action_tag="#중복_감지",
                meta={
                    "sha256_prefix":          sha256[:12],
                    "original_upload_log_id": existing_log.pk,
                    "original_filename":      file.name,
                },
            )

            logger.info("중복 파일 감지 | hash=%s | 기존 UploadLog=%s", sha256[:12], existing_log.pk)

            return Response(
                {"message_id": user_message.pk, "session_id": session.pk, "status": "duplicate"},
                status=status.HTTP_202_ACCEPTED,
            )

        # ── 신규 파일: FileStructure 생성 또는 조회 ──────────────────────────────
        source_type = _SUFFIX_TO_SOURCE_TYPE[suffix]

        if suffix in (".xlsx", ".xls"):
            col_names = extract_excel_columns(abs_path)
            hash_value = compute_file_structure_hash(col_names)
            col_schema = col_names
        elif suffix == ".csv":
            col_names = extract_csv_columns(abs_path)
            hash_value = compute_file_structure_hash(col_names)
            col_schema = col_names
        elif suffix == ".pdf":
            hash_value = pdf_structure_hash(file.name)
            col_schema = []
        else:
            # DOCX / PPTX / HWP / 이미지 — 파일명 패턴 기반 fingerprint
            hash_value = generic_structure_hash(suffix, file.name)
            col_schema = []

        file_structure, _ = FileStructure.objects.get_or_create(
            hash=hash_value,
            defaults={"source_type": source_type, "column_schema": col_schema},
        )

        upload_log = UploadLog.objects.create(
            user=request.user,
            file_structure=file_structure,
            original_filename=file.name,
            status=UploadLog.Status.PENDING,
            file_hash=sha256,
            file=saved_rel,   # 상대 경로 직접 저장 → file.url = /media/uploads/...
        )

        user_message.upload_log = upload_log
        user_message.save(update_fields=["upload_log"])

        task = current_app.send_task(
            "tasks.analyze_document",
            kwargs={
                "file_path": abs_path,
                "upload_id": upload_log.pk,
                "chat_message_id": user_message.pk,
            },
            queue="ax",
        )

        upload_log.ax_task_id = task.id
        upload_log.status = UploadLog.Status.PROCESSING
        upload_log.save(update_fields=["ax_task_id", "status"])

        # ── 신규 업로드 행동 로그 ─────────────────────────────────────────────
        _file_type = _SUFFIX_TO_FILE_TYPE.get(suffix, UserActionLog.FileType.UNKNOWN)
        _file_bytes = 0
        try:
            _file_bytes = upload_log.file.size
        except Exception:
            pass

        UserActionLog.objects.create(
            user=request.user,
            session=session,
            upload_log=upload_log,
            action_type=UserActionLog.ActionType.FILE_UPLOAD,
            file_type=_file_type,
            action_tag="#파일_업로드",
            meta={
                "original_filename": file.name,
                "file_bytes":        _file_bytes,
                "ax_task_id":        task.id,
            },
        )

        logger.info(
            "채팅 파일 분석 디스패치 | session=%s | user_msg=%s | task=%s",
            session.pk, user_message.pk, task.id,
        )

        return Response(
            {"message_id": user_message.pk, "session_id": session.pk, "status": "processing"},
            status=status.HTTP_202_ACCEPTED,
        )


class PptxPatchView(APIView):
    """
    AI 명령 기반 PPTX 특정 셰이프 텍스트 수정 + 슬라이드 재렌더링.

    POST /api/chat/pptx-patch/
    Request body:
      {
        "upload_log_id": 123,
        "patches": [
          {
            "slide_index": 2,       // 0-based
            "shape_index": 0,       // 셰이프 순번 (pptx_structured 기준)
            "type": "text",         // "text" | "table_cell"
            "new_text": "새 제목",
            // type=table_cell 추가 필드:
            "row_index": 1,
            "col_index": 2
          }
        ]
      }
    Response:
      {
        "updated_slides": {
          "2": "/media/slides/123/slide_3.png?v=1718400000"
        },
        "version": 1718400000
      }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from pathlib import Path as Pth
        import time
        from apps.documents.models import UploadLog
        from apps.documents.pptx_render import render_one_slide

        upload_log_id = request.data.get("upload_log_id")
        patches       = request.data.get("patches", [])

        if not upload_log_id or not patches:
            return Response(
                {"error": "upload_log_id 와 patches 는 필수입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            upload_log = UploadLog.objects.get(pk=upload_log_id, user=request.user)
        except UploadLog.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not upload_log.file:
            return Response(
                {"error": "원본 PPTX 파일을 찾을 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        abs_path = Pth(str(settings.MEDIA_ROOT)) / upload_log.file.name

        try:
            from pptx import Presentation
        except ImportError:
            return Response(
                {"error": "python-pptx 미설치 — pip install python-pptx"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        prs = Presentation(str(abs_path))
        affected_slides: set[int] = set()

        for patch in patches:
            slide_idx  = int(patch.get("slide_index", 0))
            shape_idx  = int(patch.get("shape_index", 0))
            patch_type = patch.get("type", "text")
            new_text   = str(patch.get("new_text", ""))

            if slide_idx >= len(prs.slides):
                continue
            slide = prs.slides[slide_idx]
            if shape_idx >= len(slide.shapes):
                continue
            shape = slide.shapes[shape_idx]

            if patch_type == "text" and shape.has_text_frame:
                tf = shape.text_frame
                # 첫 번째 단락 텍스트 교체 (서식 일부 보존)
                if tf.paragraphs:
                    para = tf.paragraphs[0]
                    for run in para.runs:
                        run.text = ""
                    if para.runs:
                        para.runs[0].text = new_text
                    else:
                        para.text = new_text
                affected_slides.add(slide_idx)

            elif patch_type == "table_cell" and shape.has_table:
                row_idx = int(patch.get("row_index", 0))
                col_idx = int(patch.get("col_index", 0))
                tbl = shape.table
                if row_idx < len(tbl.rows) and col_idx < len(tbl.rows[row_idx].cells):
                    cell_tf = tbl.rows[row_idx].cells[col_idx].text_frame
                    if cell_tf.paragraphs:
                        cell_tf.paragraphs[0].text = new_text
                affected_slides.add(slide_idx)

        # 수정된 PPTX 덮어쓰기
        prs.save(str(abs_path))

        # 변경된 슬라이드만 재렌더링
        v = int(time.time())
        updated_slides: dict[str, str] = {}
        render_errors: list[str] = []

        for slide_idx in sorted(affected_slides):
            try:
                url = render_one_slide(abs_path, upload_log.pk, slide_idx)
                updated_slides[str(slide_idx)] = url
            except Exception as e:
                render_errors.append(f"슬라이드 {slide_idx}: {e}")
                logger.warning("슬라이드 재렌더링 실패 | slide=%s | err=%s", slide_idx, e)

        response_data: dict = {"updated_slides": updated_slides, "version": v}
        if render_errors:
            response_data["render_errors"] = render_errors

        return Response(response_data, status=status.HTTP_200_OK)
