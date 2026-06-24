import json
import logging
import os
import re
from pathlib import Path

from celery import current_app
from celery.result import AsyncResult
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FileStructure, InboundEmail, IngestionWorkflow, UploadLog, compute_file_structure_hash, pdf_structure_hash
from .serializers import InboundEmailSerializer, IngestionWorkflowSerializer, UploadLogSerializer, WorkflowActivateSerializer
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

        upload_log = UploadLog.objects.create(
            user=request.user,
            file_structure=file_structure,
            original_filename=uploaded_file.name,
            status=UploadLog.Status.PENDING,
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
    대시보드 통계 응답.
    - 토큰/잔액 필드: 현재 결제 모델 없으므로 하드코딩 (추후 결제 앱 연동 시 대체)
    - monthly_processed/errors: UploadLog DB 집계 (이번 달, 본인 것만)
    """

    permission_classes = [IsAuthenticated]

    # 토큰·결제 관련 필드는 결제 모델 구현 전 임시 고정값
    _HARDCODED = {
        "token_used":    716000,
        "token_total":   2000000,
        "balance":       312000,
        "deposit":       500000,
        "monthly_spent": 188000,
    }

    def get(self, request):
        from django.utils import timezone

        now = timezone.now()
        # 이번 달 1일 00:00:00 기준으로 필터링
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_qs = UploadLog.objects.filter(
            user=request.user,
            uploaded_at__gte=month_start,
        )
        monthly_processed = base_qs.filter(status=UploadLog.Status.DONE).count()
        monthly_errors = base_qs.filter(status=UploadLog.Status.FAILED).count()
        monthly_corrected = monthly_processed - monthly_errors

        return Response({
            **self._HARDCODED,
            "monthly_processed": monthly_processed,
            "monthly_errors":    monthly_errors,
            "monthly_corrected": monthly_corrected,
        })


class EmailInboxView(ListAPIView):
    """GET /api/v1/email-inbox/ — 본인 수신 이메일 이력 목록."""

    serializer_class = InboundEmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InboundEmail.objects.filter(user=self.request.user)


def _sync_task_result(upload_log: UploadLog) -> None:
    """Celery 결과 백엔드에서 태스크 상태를 DB로 동기화."""
    result = AsyncResult(upload_log.ax_task_id)
    if result.successful():
        upload_log.result = result.get()
        upload_log.status = UploadLog.Status.DONE
        upload_log.save(update_fields=["result", "status"])
    elif result.failed():
        upload_log.status = UploadLog.Status.FAILED
        upload_log.save(update_fields=["status"])
