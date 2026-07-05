import json
import logging
import os
import re
import uuid
from pathlib import Path

from celery import current_app
from celery.result import AsyncResult
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DocumentChange, DocumentVersion, FileStructure, InboundEmail, IngestionWorkflow, UploadLog, UsageEvent, compute_file_structure_hash, pdf_structure_hash
from .services.patch_plan import LLMParseError, PatchPlanService
from .services.usage import (
    analysis_status_for_result,
    credit_limit_response,
    is_unsupported_scan_result,
    record_usage_event,
    usage_metadata_from_result,
)
from .tasks import patch_document_version
from .serializers import (
    DocumentChangeSerializer,
    DocumentVersionCreateSerializer,
    DocumentVersionSummarySerializer,
    InboundEmailSerializer,
    IngestionWorkflowSerializer,
    UploadLogSerializer,
    WorkflowActivateSerializer,
)
from .utils import extract_excel_columns, save_temp_file

logger = logging.getLogger(__name__)


class DocumentUploadView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]
    _ALLOWED_SUFFIXES = {".xlsx", ".pdf"}

    @extend_schema(
        summary="파일 업로드 및 AI 분석 시작",
        description="Excel(.xlsx) 또는 PDF 파일을 업로드하면 AX Engine 비동기 태스크가 시작됩니다.",
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={
            202: OpenApiResponse(description="태스크 접수 완료", examples=[OpenApiExample("성공", value={"upload_id": 1, "task_id": "abc-123"})]),
            400: OpenApiResponse(description="파일 누락 또는 미지원 형식"),
        },
    )
    def post(self, request):
        # 베타 크레딧 한도 — 파일 저장·태스크 예약 전에 차단해야 부산물이 남지 않는다
        blocked = credit_limit_response(request.user)
        if blocked:
            return blocked

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "file 필드가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix not in self._ALLOWED_SUFFIXES:
            return Response(
                {"error": f"지원 형식: {', '.join(self._ALLOWED_SUFFIXES)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tmp_path = save_temp_file(uploaded_file, suffix)

        file_structure = self._get_or_create_file_structure(tmp_path, suffix, uploaded_file.name)

        # save_temp_file이 파일 포인터를 끝까지 읽으므로 seek(0) 후 원본 저장
        uploaded_file.seek(0)
        upload_log = UploadLog.objects.create(
            user=request.user,
            file_structure=file_structure,
            original_filename=uploaded_file.name,
            status=UploadLog.Status.PENDING,
            file=uploaded_file,
        )

        # 문자열 기반 send_task로 ax-engine 패키지를 직접 import하지 않는다.
        # Django ↔ AX Engine 간 물리적 결합을 브로커(Redis)로만 유지하는 핵심 설계.
        task = current_app.send_task(
            "tasks.analyze_document",
            kwargs={"file_path": tmp_path, "upload_id": upload_log.pk},
        )

        upload_log.ax_task_id = task.id
        upload_log.status = UploadLog.Status.PROCESSING
        upload_log.save(update_fields=["ax_task_id", "status"])

        return Response(
            {"upload_id": upload_log.pk, "task_id": task.id},
            status=status.HTTP_202_ACCEPTED,
        )

    @staticmethod
    def _get_or_create_file_structure(tmp_path: str, suffix: str, filename: str) -> FileStructure:
        if suffix == ".xlsx":
            col_names = extract_excel_columns(tmp_path)
            hash_value = compute_file_structure_hash(col_names)
            source_type = FileStructure.SourceType.EXCEL
        else:
            col_names = []
            hash_value = pdf_structure_hash(filename)
            source_type = FileStructure.SourceType.PDF

        file_structure, _ = FileStructure.objects.get_or_create(
            hash=hash_value,
            defaults={"source_type": source_type, "column_schema": col_names},
        )
        return file_structure


class UploadResultView(RetrieveAPIView):
    """
    GET /api/v1/uploads/<id>/
    Celery 결과 백엔드를 폴링하여 최신 상태로 동기화 후 반환.
    완료/실패 상태는 DB에 캐시되므로 중복 조회 시 백엔드 호출 없음.
    """

    serializer_class = UploadLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UploadLog.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        terminal_statuses = {UploadLog.Status.DONE, UploadLog.Status.FAILED}
        if instance.status not in terminal_statuses and instance.ax_task_id:
            _sync_task_result(instance)

        return Response(self.get_serializer(instance).data)


class UploadListView(ListAPIView):
    """GET /api/v1/uploads/ — 본인 업로드 이력 목록"""

    serializer_class = UploadLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UploadLog.objects.filter(user=self.request.user).select_related("file_structure")


class WorkflowListView(ListAPIView):
    """GET /api/v1/workflows/ — 제안되거나 활성화된 자동화 워크플로우 목록"""

    serializer_class = IngestionWorkflowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IngestionWorkflow.objects.filter(
            user=self.request.user, is_suggested=True
        ).select_related("file_structure")


class WorkflowActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="자동화 워크플로우 활성화",
        description="카카오 알림톡 채널과 수신 전화번호를 등록하고 인바운드 이메일을 발급합니다.",
        request=WorkflowActivateSerializer,
        responses={
            200: OpenApiResponse(description="활성화 완료", examples=[OpenApiExample("성공", value={"inbound_email": "user-1-abc123@officeax.com"})]),
            404: OpenApiResponse(description="워크플로우 없음"),
        },
    )

    def post(self, request, pk: int):
        try:
            workflow = IngestionWorkflow.objects.get(pk=pk, user=request.user)
        except IngestionWorkflow.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if workflow.is_active:
            return Response(
                {"inbound_email": workflow.inbound_email},
                status=status.HTTP_200_OK,
            )

        serializer = WorkflowActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workflow.activate(
            channel=serializer.validated_data["channel"],
            phone_number=serializer.validated_data.get("phone_number", ""),
        )

        return Response(
            {"inbound_email": workflow.inbound_email},
            status=status.HTTP_200_OK,
        )


class InboundEmailWebhookView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [MultiPartParser]
    _ALLOWED_SUFFIXES = {".xlsx", ".pdf"}

    @extend_schema(exclude=True)   # 내부 웹훅 — Swagger 문서에서 숨김
    def post(self, request):
        if not self._verify_webhook_token(request):
            return Response(status=status.HTTP_403_FORBIDDEN)

        to_email = self._parse_recipient(request)
        if not to_email:
            logger.warning("inbound-email 웹훅: 수신자 이메일 파싱 실패")
            return Response({"error": "수신자 주소를 파싱할 수 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            workflow = (
                IngestionWorkflow.objects
                .select_related("user", "file_structure")
                .get(inbound_email=to_email, is_active=True)
            )
        except IngestionWorkflow.DoesNotExist:
            # 미등록·비활성 주소는 정보 노출 없이 200 반환
            logger.info("inbound-email 웹훅: 미등록/비활성 수신자 주소=%s", to_email)
            return Response(status=status.HTTP_200_OK)

        processed = 0
        first_upload_log = None  # 이메일 이력에 연결할 첫 번째 UploadLog
        first_filename = ""

        for file_obj, filename in self._iter_attachments(request):
            suffix = Path(filename).suffix.lower()
            if suffix not in self._ALLOWED_SUFFIXES:
                logger.info("inbound-email 웹훅: 미지원 형식 스킵 | 파일=%s", filename)
                continue

            tmp_path = save_temp_file(file_obj, suffix)

            upload_log = UploadLog.objects.create(
                user=workflow.user,
                file_structure=workflow.file_structure,
                original_filename=filename,
                status=UploadLog.Status.PENDING,
            )

            task = current_app.send_task(
                "tasks.analyze_document",
                kwargs={"file_path": tmp_path, "upload_id": upload_log.pk},
            )
            upload_log.ax_task_id = task.id
            upload_log.status = UploadLog.Status.PROCESSING
            upload_log.save(update_fields=["ax_task_id", "status"])

            if processed == 0:
                # 첫 번째 첨부파일 정보를 이메일 이력에 기록
                first_upload_log = upload_log
                first_filename = filename
            processed += 1

        # 수신 이메일 이력을 DB에 저장 (첨부파일이 없어도 기록)
        self._save_inbound_email_record(workflow, request, first_filename, first_upload_log)

        logger.info(
            "inbound-email 웹훅 처리 완료 | user_id=%s | 첨부파일=%d건",
            workflow.user_id, processed,
        )
        return Response({"processed_attachments": processed}, status=status.HTTP_200_OK)

    @staticmethod
    def _save_inbound_email_record(
        workflow: IngestionWorkflow,
        request,
        first_filename: str,
        upload_log: UploadLog | None,
    ) -> None:
        """수신 이메일 이력 레코드를 생성한다. 실패해도 웹훅 응답에 영향 없음."""
        try:
            sender = request.data.get("from", "")
            subject = request.data.get("subject", "")
            InboundEmail.objects.create(
                workflow=workflow,
                user=workflow.user,
                sender=sender,
                subject=subject,
                attachment_filename=first_filename,
                upload_log=upload_log,
            )
        except Exception:
            logger.exception("InboundEmail 레코드 생성 실패 | user_id=%s", workflow.user_id)

    @staticmethod
    def _verify_webhook_token(request) -> bool:
        secret = os.environ.get("INBOUND_WEBHOOK_SECRET", "")
        if not secret:
            return True   # 개발 환경: 시크릿 미설정 시 검증 스킵
        received = (
            request.query_params.get("token")
            or request.headers.get("X-Webhook-Token", "")
        )
        return received == secret

    @staticmethod
    def _parse_recipient(request) -> str | None:
        """SendGrid envelope JSON → 수신자 이메일 소문자 정규화."""
        try:
            envelope = json.loads(request.data.get("envelope", "{}"))
            to_list = envelope.get("to", [])
            if to_list:
                return to_list[0].strip().lower()
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        # fallback: to 필드 직접 파싱 (Name <email> 형식 대응)
        raw_to = request.data.get("to", "")
        match = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", raw_to)
        return match.group(0).lower() if match else None

    @staticmethod
    def _iter_attachments(request):
        """
        SendGrid Inbound Parse 첨부파일 이터레이터.
        attachment-info JSON으로 원본 파일명을 복원한다.
        """
        try:
            attachment_info: dict = json.loads(request.data.get("attachment-info", "{}"))
        except (json.JSONDecodeError, TypeError):
            attachment_info = {}

        num_attachments = int(request.data.get("attachments", 0))
        for i in range(1, num_attachments + 1):
            key = f"attachment{i}"
            file_obj = request.FILES.get(key)
            if file_obj is None:
                continue
            info = attachment_info.get(key, {})
            filename = info.get("filename") or getattr(file_obj, "name", None) or key
            yield file_obj, filename


class EmailInboxAttachmentView(APIView):
    """
    GET /api/v1/email-inbox/:id/attachment/
    수신 이메일에 연결된 업로드 파일 URL을 반환한다.
    upload_log 또는 파일이 없으면 404.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        try:
            inbox = InboundEmail.objects.select_related("upload_log").get(
                pk=pk, user=request.user
            )
        except InboundEmail.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        upload_log = inbox.upload_log
        if upload_log is None or not upload_log.file:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 파일이 실제로 디스크에 존재하는지 확인
        file_url = ""
        try:
            if upload_log.file.storage.exists(upload_log.file.name):
                file_url = upload_log.file.url
        except Exception:
            pass

        return Response({
            "file_url": file_url,
            "original_filename": upload_log.original_filename,
        })


class DashboardStatsView(APIView):
    """
    GET /api/v1/dashboard/stats/
    UsageEvent 기반 이번 달 사용량 통계 응답.
    """

    permission_classes = [IsAuthenticated]

    def _get_monthly_limits(self, user):
        """
        이번 달 토큰/비용 한도를 반환한다.

        MVP에서는 settings의 전역 고정값을 쓰지만, 메서드로 분리해 두어
        추후 User→Plan→limit 구조로 교체할 때 이 메서드만 바꾸면 되게 한다.
        """
        return settings.MONTHLY_TOKEN_LIMIT, settings.MONTHLY_COST_LIMIT_KRW

    def get(self, request):
        from django.utils import timezone

        monthly_token_limit, monthly_cost_limit = self._get_monthly_limits(request.user)
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        usage_qs = UsageEvent.objects.filter(
            user=request.user,
            created_at__gte=month_start,
        )

        totals = usage_qs.aggregate(
            ai_calls=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            estimated_cost=Sum("estimated_cost"),
            failed_jobs=Count("id", filter=Q(status=UsageEvent.Status.FAILED)),
            processed_documents=Count(
                "upload_log",
                filter=Q(event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS, status=UsageEvent.Status.SUCCESS),
                distinct=True,
            ),
            generated_revisions=Count(
                "document_version",
                filter=Q(event_type=UsageEvent.EventType.PATCH_ARTIFACT_GENERATION, status=UsageEvent.Status.SUCCESS),
                distinct=True,
            ),
        )
        input_tokens = totals["input_tokens"] or 0
        output_tokens = totals["output_tokens"] or 0
        total_tokens = input_tokens + output_tokens
        estimated_cost = totals["estimated_cost"] or 0
        token_percent = min(round(total_tokens / monthly_token_limit * 100), 100)
        cost_percent = min(round(float(estimated_cost) / monthly_cost_limit * 100), 100)

        return Response({
            "month_start": month_start.date().isoformat(),
            "ai_calls": totals["ai_calls"] or 0,
            "processed_documents": totals["processed_documents"] or 0,
            "generated_revisions": totals["generated_revisions"] or 0,
            "failed_jobs": totals["failed_jobs"] or 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "token_source_counts": {
                source: usage_qs.filter(token_source=source).count()
                for source, _label in UsageEvent.TokenSource.choices
            },
            "estimated_cost": int(estimated_cost),
            "monthly_token_limit": monthly_token_limit,
            "monthly_cost_limit": monthly_cost_limit,
            "token_usage_percent": token_percent,
            "cost_usage_percent": cost_percent,
            # 기존 프론트/테스트 호환 필드. 값은 더 이상 하드코딩이 아니다.
            "token_used": total_tokens,
            "token_total": monthly_token_limit,
            "balance": max(monthly_cost_limit - int(estimated_cost), 0),
            "deposit": monthly_cost_limit,
            "monthly_spent": int(estimated_cost),
            "monthly_processed": totals["processed_documents"] or 0,
            "monthly_errors": totals["failed_jobs"] or 0,
            "monthly_corrected": totals["generated_revisions"] or 0,
        })


class EmailInboxView(ListAPIView):
    """GET /api/v1/email-inbox/ — 본인 수신 이메일 이력 목록."""

    serializer_class = InboundEmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InboundEmail.objects.filter(user=self.request.user)


# ── 상태 전이 허용 집합 ───────────────────────────────────────────────────────
# pending ↔ applied / pending ↔ rejected 만 허용.
# applied ↔ rejected 직접 전이, failed 전이는 금지.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending":  {"applied", "rejected"},
    "applied":  {"pending"},
    "rejected": {"pending"},
}


class DocumentChangeListView(ListAPIView):
    """
    GET /api/v1/uploads/{upload_id}/changes/
    해당 UploadLog의 DocumentChange 목록 반환.
    본인 소유 upload만 허용 (타인 소유면 404).
    ?version_id= 로 특정 버전 필터링 가능.
    """

    serializer_class = DocumentChangeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 본인 소유 UploadLog인지 확인 — 아니면 404
        upload_log = self._get_upload_or_404()
        qs = DocumentChange.objects.filter(
            version__upload_log=upload_log
        ).select_related("version")

        # 특정 버전 필터 옵션
        version_id = self.request.query_params.get("version_id")
        if version_id:
            qs = qs.filter(version_id=version_id)

        return qs

    def _get_upload_or_404(self) -> UploadLog:
        try:
            return UploadLog.objects.get(
                pk=self.kwargs["upload_id"],
                user=self.request.user,
            )
        except UploadLog.DoesNotExist:
            raise NotFound()


class DocumentChangePatchView(APIView):
    """
    PATCH /api/v1/changes/{id}/
    DocumentChange 단건 status 변경.
    허용 전이: pending ↔ applied, pending ↔ rejected.
    그 외 전이는 400 반환.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        change = self._get_change_or_403(pk)

        new_status = request.data.get("status")
        if new_status not in _ALLOWED_TRANSITIONS.get(change.status, set()):
            return Response(
                {"detail": "허용되지 않는 상태 전이입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        change.status = new_status
        change.save(update_fields=["status", "updated_at"])

        return Response(DocumentChangeSerializer(change).data, status=status.HTTP_200_OK)

    def _get_change_or_403(self, pk: int) -> DocumentChange:
        """change 조회. 존재하지 않으면 404, 타인 소유면 403."""
        try:
            change = DocumentChange.objects.select_related(
                "version__upload_log"
            ).get(pk=pk)
        except DocumentChange.DoesNotExist:
            raise NotFound()

        if change.version.upload_log.user_id != self.request.user.pk:
            raise PermissionDenied()

        return change


def _resolve_owned_version(
    user, upload_id: int, version_id: int, *, select_related: tuple[str, ...] = ("upload_log",)
) -> DocumentVersion:
    """버전 소유권 검증 공통 헬퍼. 없거나 upload_log에 속하지 않으면 404, 타인 소유면 403을 raise한다."""
    try:
        version = (
            DocumentVersion.objects
            .select_related(*select_related)
            .get(pk=version_id, upload_log_id=upload_id)
        )
    except DocumentVersion.DoesNotExist:
        raise NotFound()

    if version.upload_log.user_id != user.pk:
        raise PermissionDenied()

    return version


class DocumentChangeAcceptAllView(APIView):
    """
    POST /api/v1/uploads/{upload_id}/versions/{version_id}/changes/accept-all/

    해당 버전의 pending DocumentChange를 전부 조회해 anchor 기준으로 그룹핑한다.
    같은 anchor를 가리키는 pending 변경이 여러 개면(충돌) confidence가 가장 높은
    하나만 applied로, 나머지는 rejected로 자동 처리한다. 동점이면 operation_id
    오름차순으로 먼저 오는 쪽이 승자다. 빈 anchor({})는 위치 정보가 없어
    충돌 판단이 불가능하므로 그룹핑하지 않고 항상 단독 applied 처리한다.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, upload_id: int, version_id: int):
        version = _resolve_owned_version(request.user, upload_id, version_id)

        # change_ids가 오면 부분 선택 반영 — 채팅 말풍선 체크박스 UX.
        # 선택되지 않은 pending은 건드리지 않는다 (보류 유지).
        change_ids = request.data.get("change_ids")
        if change_ids is not None and (
            not isinstance(change_ids, list)
            or not all(isinstance(cid, int) and not isinstance(cid, bool) for cid in change_ids)
        ):
            return Response(
                {"error": "change_ids는 정수 리스트여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pending_qs = DocumentChange.objects.filter(
            version=version, status=DocumentChange.Status.PENDING
        )
        if change_ids is not None:
            # version 스코프 안에서만 필터 — 타 버전 id는 자연히 무시된다
            pending_qs = pending_qs.filter(pk__in=change_ids)
        pending_changes = list(pending_qs)

        applied, rejected = self._resolve_conflicts(pending_changes)

        with transaction.atomic():
            for change in applied:
                change.status = DocumentChange.Status.APPLIED
                change.save(update_fields=["status", "updated_at"])
            for change in rejected:
                change.reason = f"{change.reason}\n[자동 반려: 동일 위치 변경 충돌, 더 높은 신뢰도 변경 채택]"
                change.status = DocumentChange.Status.REJECTED
                change.save(update_fields=["status", "reason", "updated_at"])

        return Response({
            "applied": DocumentChangeSerializer(applied, many=True).data,
            "rejected": DocumentChangeSerializer(rejected, many=True).data,
        })

    @staticmethod
    def _resolve_conflicts(
        pending_changes: list["DocumentChange"],
    ) -> tuple[list["DocumentChange"], list["DocumentChange"]]:
        """
        anchor 기준으로 그룹핑 후 그룹별 승자/패자를 결정한다.
        빈 anchor({})는 항상 단독 그룹으로 취급한다.
        """
        groups: dict[str, list["DocumentChange"]] = {}
        for idx, change in enumerate(pending_changes):
            if not change.anchor:
                # 빈 anchor는 충돌 판단이 불가능하므로 항상 단독 그룹으로 처리
                key = f"__empty_anchor_{idx}__"
            else:
                key = json.dumps(change.anchor, sort_keys=True)
            groups.setdefault(key, []).append(change)

        applied: list["DocumentChange"] = []
        rejected: list["DocumentChange"] = []
        for group in groups.values():
            if len(group) == 1:
                applied.append(group[0])
                continue
            # 충돌 그룹 — confidence 내림차순, 동점이면 operation_id 오름차순으로 승자 결정
            winner = min(group, key=lambda c: (-c.confidence, c.operation_id))
            applied.append(winner)
            rejected.extend(c for c in group if c is not winner)

        return applied, rejected


class DocumentVersionCreateView(APIView):
    """
    GET  /api/v1/uploads/{upload_id}/versions/ — 버전 목록 반환
    POST /api/v1/uploads/{upload_id}/versions/ — 새 DocumentVersion 생성 (draft 상태 고정)

    version_number는 모델 save()에서 자동 채번.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, upload_id: int):
        """소유자의 업로드에 속한 버전 목록을 반환한다."""
        upload_log = self._get_upload_or_403(upload_id)
        versions = DocumentVersion.objects.filter(upload_log=upload_log).order_by("version_number")
        return Response(DocumentVersionSummarySerializer(versions, many=True).data)

    def post(self, request, upload_id: int):
        upload_log = self._get_upload_or_403(upload_id)

        serializer = DocumentVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        version = DocumentVersion.objects.create(
            upload_log=upload_log,
            created_by=request.user,
            **serializer.validated_data,
        )

        return Response(
            DocumentVersionSummarySerializer(version).data,
            status=status.HTTP_201_CREATED,
        )

    def _get_upload_or_403(self, upload_id: int) -> UploadLog:
        """upload 조회. 존재하지 않으면 404, 타인 소유면 403."""
        try:
            upload_log = UploadLog.objects.get(pk=upload_id)
        except UploadLog.DoesNotExist:
            raise NotFound()

        if upload_log.user_id != self.request.user.pk:
            raise PermissionDenied()

        return upload_log


# on-demand 파일 반환 시 source_type → MIME 타입 매핑
_MIME_BY_SOURCE_TYPE: dict[str, str] = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx":  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx":  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf":   "application/pdf",
    "hwp":   "application/x-hwp",
    "hwpx":  "application/x-hwp",
}

# source_type → 파일 확장자 매핑
_EXT_BY_SOURCE_TYPE: dict[str, str] = {
    "excel": ".xlsx",
    "docx":  ".docx",
    "pptx":  ".pptx",
    "pdf":   ".pdf",
    "hwp":   ".hwp",
    "hwpx":  ".hwpx",
}


class DocumentVersionFileView(APIView):
    """
    GET /api/v1/uploads/{upload_id}/versions/{version_id}/file/

    patch_document_version task가 저장해 둔 artifact_file을 그대로 반환한다.
    재생성하지 않으므로 이 메서드는 DB write를 전혀 수행하지 않는다(멱등).

    status != ready → 409 Conflict
    ready 상태인데 artifact_file이 비어있는 경우(방어적 경계 케이스) → 404 Not Found
    타인 소유 → 403 Forbidden
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, upload_id: int, version_id: int):
        version = _resolve_owned_version(
            request.user, upload_id, version_id,
            select_related=("upload_log", "upload_log__file_structure"),
        )
        upload_log = version.upload_log

        if version.status != DocumentVersion.Status.READY:
            return Response(
                {"detail": "ready 상태 버전만 파일을 반환할 수 있습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        if not version.artifact_file:
            return Response(
                {"detail": "파일이 아직 생성되지 않았습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        source_type = upload_log.file_structure.source_type if upload_log.file_structure else ""
        mime = _MIME_BY_SOURCE_TYPE.get(source_type, "application/octet-stream")
        ext = _EXT_BY_SOURCE_TYPE.get(source_type, "")
        filename = f"version_{version_id}{ext}"

        from django.http import HttpResponse
        with version.artifact_file.open("rb") as f:
            file_bytes = f.read()
        response = HttpResponse(file_bytes, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class DocumentVersionPatchTriggerView(APIView):
    """
    POST /api/v1/uploads/{upload_id}/versions/{version_id}/patch/
    draft 버전에 대해 XLSX 패치 태스크를 트리거한다.

    소유권: version.upload_log.user != request.user → 403
    상태 제약: version.status != 'draft' → 400
    성공: status=generating으로 전이 후 Celery 태스크 예약 → 202
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, upload_id: int, version_id: int):
        # 베타 크레딧 한도 — 소유권 조회보다 먼저 차단 (값싼 체크 우선)
        blocked = credit_limit_response(request.user)
        if blocked:
            return blocked

        version = _resolve_owned_version(request.user, upload_id, version_id)

        if version.status != DocumentVersion.Status.DRAFT:
            return Response(
                {"detail": "draft 상태의 버전만 패치 트리거가 가능합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        version.status = DocumentVersion.Status.GENERATING
        version.save(update_fields=["status", "updated_at"])

        patch_document_version.delay(version.pk)

        return Response(
            DocumentVersionSummarySerializer(version).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentVersionDeleteView(APIView):
    """
    DELETE /api/v1/uploads/{upload_id}/versions/{version_id}/

    명시적으로 버전을 삭제한다. storage의 artifact_file 정리는
    DocumentVersion의 pre_delete 시그널에 위임한다(models.py 참조).

    소유권: version.upload_log.user != request.user → 403
    상태 제약: status=original → 400(원본 버전 보호)
              status=generating → 409(패치 작업 중 레이스 컨디션 방지)
    성공: row 삭제 → 204
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, upload_id: int, version_id: int):
        version = _resolve_owned_version(request.user, upload_id, version_id)

        if version.status == DocumentVersion.Status.ORIGINAL:
            return Response(
                {"detail": "원본 버전은 삭제할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if version.status == DocumentVersion.Status.GENERATING:
            return Response(
                {"detail": "생성 중인 버전은 삭제할 수 없습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        version.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


def _sync_task_result(upload_log: UploadLog) -> None:
    """Celery 결과 백엔드에서 태스크 상태를 DB로 동기화."""
    result = AsyncResult(upload_log.ax_task_id)
    if result.successful():
        payload = result.get()
        upload_log.result = payload
        upload_log.status = UploadLog.Status.DONE
        upload_log.save(update_fields=["result", "status"])
        # 스캔본(미지원)은 FAILED + error_code로 기록해 크레딧 차감에서 제외한다
        record_usage_event(
            user=upload_log.user,
            upload_log=upload_log,
            event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
            status=analysis_status_for_result(payload),
            metadata=usage_metadata_from_result(
                payload,
                source="upload_result_polling",
                error_code="unsupported_scan" if is_unsupported_scan_result(payload) else None,
            ),
        )
    elif result.failed():
        upload_log.status = UploadLog.Status.FAILED
        upload_log.save(update_fields=["status"])
        record_usage_event(
            user=upload_log.user,
            upload_log=upload_log,
            event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
            status=UsageEvent.Status.FAILED,
            metadata={"source": "upload_result_polling", "task_id": upload_log.ax_task_id},
        )


# ── Patch Plan 관련 상수/오류 타입은 services.patch_plan으로 이전 ──────────────
# LLMParseError, _XLSX_FORMAT_OPERATIONS, _PATCH_PLAN_SYSTEM_PROMPT,
# _generate_patch_plan, _build_file_context, _create_changes →
# apps.documents.services.patch_plan 참조


# ── Patch Plan 생성 API ───────────────────────────────────────────────────────


class GeneratePatchPlanView(APIView):
    """
    POST /api/v1/uploads/{upload_id}/generate-patch-plan/

    PatchPlanService.generate()에 위임해 DocumentVersion(draft) + DocumentChange를 저장한다.

    소유권: upload_log.user != request.user → 403
    상태 제약: upload_log.status != DONE → 400
    LLM 실패: JSON 파싱 오류 → 400
    빈 operations: 200 + {"changes": [], "version_id": null}
    성공: 201 + {"version_id": int, "plan_id": str, "changes": [...]}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, upload_id: int):
        # 베타 크레딧 한도 — LLM 호출 전 차단
        blocked = credit_limit_response(request.user)
        if blocked:
            return blocked

        upload_log = UploadLog.objects.filter(pk=upload_id).select_related("user").first()
        # 소유권 사전 검증 — PermissionError/DoesNotExist는 서비스에서 raise
        try:
            result = PatchPlanService.generate(
                upload_id=upload_id,
                prompt=(request.data.get("prompt") or "").strip(),
                user=request.user,
            )
        except UploadLog.DoesNotExist:
            record_usage_event(
                user=request.user,
                event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
                status=UsageEvent.Status.FAILED,
                metadata={"upload_id": upload_id, "reason": "upload_not_found", "source": "api"},
            )
            raise NotFound()
        except PermissionError:
            record_usage_event(
                user=request.user,
                upload_log=upload_log,
                event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
                status=UsageEvent.Status.FAILED,
                metadata={"upload_id": upload_id, "reason": "permission_denied", "source": "api"},
            )
            raise PermissionDenied()
        except ValueError as exc:
            record_usage_event(
                user=request.user,
                upload_log=upload_log,
                event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
                status=UsageEvent.Status.FAILED,
                metadata={"upload_id": upload_id, "reason": str(exc), "source": "api"},
            )
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LLMParseError:
            record_usage_event(
                user=request.user,
                upload_log=upload_log,
                event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
                status=UsageEvent.Status.FAILED,
                metadata={"upload_id": upload_id, "reason": "llm_parse_error", "source": "api"},
            )
            return Response(
                {"detail": "LLM이 유효한 patch plan을 생성하지 못했습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # prompt 빈 값 검증은 서비스 호출 전에도 할 수 있지만,
        # 서비스는 빈 prompt를 LLM에 전달 후 빈 operations를 반환할 것이므로
        # 여기서는 status code 결정만 담당한다.
        if result["version_id"] is None:
            record_usage_event(
                user=request.user,
                upload_log=upload_log,
                event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
                status=UsageEvent.Status.SUCCESS,
                metadata={"upload_id": upload_id, "version_id": None, "changes": 0, "source": "api"},
            )
            return Response(result, status=status.HTTP_200_OK)

        record_usage_event(
            user=request.user,
            upload_log=upload_log,
            document_version=DocumentVersion.objects.filter(pk=result["version_id"]).first(),
            event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
            status=UsageEvent.Status.SUCCESS,
            metadata={"upload_id": upload_id, "version_id": result["version_id"], "changes": len(result.get("changes", [])), "source": "api"},
        )
        return Response(result, status=status.HTTP_201_CREATED)
