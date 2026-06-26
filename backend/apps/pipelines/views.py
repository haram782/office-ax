from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Pipeline, PipelineRun, PipelineStep
from .serializers import PipelineRunSerializer, PipelineSerializer, PipelineStepSerializer


class PipelineListCreateView(ListCreateAPIView):
    """
    GET  /api/v1/pipelines/ — 본인 파이프라인 목록
    POST /api/v1/pipelines/ — 파이프라인 생성
    """

    serializer_class = PipelineSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 본인 소유 파이프라인만 반환
        return Pipeline.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        # owner를 요청 사용자로 자동 지정
        serializer.save(owner=self.request.user)


class PipelineDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/pipelines/{id}/ — 단건 조회
    PATCH  /api/v1/pipelines/{id}/ — 부분 수정
    DELETE /api/v1/pipelines/{id}/ — 삭제
    """

    serializer_class = PipelineSerializer
    permission_classes = [IsAuthenticated]
    # PATCH만 허용하고 PUT은 비활성화
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # 본인 소유 파이프라인만 접근 가능 — 타인 접근 시 404
        return Pipeline.objects.filter(owner=self.request.user)


class StepListCreateView(ListCreateAPIView):
    """
    GET  /api/v1/pipelines/{pipeline_pk}/steps/ — step 목록 (step_order 오름차순)
    POST /api/v1/pipelines/{pipeline_pk}/steps/ — step 생성
    """

    serializer_class = PipelineStepSerializer
    permission_classes = [IsAuthenticated]

    def _get_pipeline(self):
        # 본인 소유 파이프라인만 조회 — 타인 파이프라인이면 404
        return get_object_or_404(
            Pipeline,
            pk=self.kwargs["pipeline_pk"],
            owner=self.request.user,
        )

    def get_queryset(self):
        # URL의 pipeline_pk와 소유자로 필터링하여 step 목록 반환
        return PipelineStep.objects.filter(
            pipeline__id=self.kwargs["pipeline_pk"],
            pipeline__owner=self.request.user,
        )

    def perform_create(self, serializer):
        # pipeline을 URL 파라미터로 조회하여 주입 — 클라이언트가 지정 불가
        pipeline = self._get_pipeline()
        try:
            serializer.save(pipeline=pipeline)
        except IntegrityError:
            # unique_together(pipeline, step_order) 충돌 → 400 반환
            raise ValidationError({"step_order": "이 파이프라인에 이미 같은 step_order가 존재합니다."})


class StepDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/pipelines/{pipeline_pk}/steps/{pk}/ — step 단건 조회
    PATCH  /api/v1/pipelines/{pipeline_pk}/steps/{pk}/ — step 부분 수정
    DELETE /api/v1/pipelines/{pipeline_pk}/steps/{pk}/ — step 삭제
    """

    serializer_class = PipelineStepSerializer
    permission_classes = [IsAuthenticated]
    # PATCH만 허용하고 PUT은 비활성화
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # 본인 소유 파이프라인의 step만 접근 가능 — 타인 접근 시 404
        return PipelineStep.objects.filter(
            pipeline__id=self.kwargs["pipeline_pk"],
            pipeline__owner=self.request.user,
        )


class StepReorderView(APIView):
    """
    POST /api/v1/pipelines/{pipeline_pk}/steps/reorder/

    요청 body: [{"id": 3, "step_order": 1}, {"id": 1, "step_order": 2}, ...]
    성공: 200 + 정렬된 steps 반환
    실패: 400 (id 불일치) / 404 (파이프라인 없음 또는 권한 없음)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pipeline_pk):
        # 본인 소유 파이프라인만 허용 — 타인 파이프라인이면 404
        pipeline = get_object_or_404(Pipeline, pk=pipeline_pk, owner=request.user)

        payload = request.data
        if not isinstance(payload, list):
            return Response({"detail": "list 형식이어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 요청에 포함된 id 집합
        requested_ids = {item.get("id") for item in payload}

        # 해당 파이프라인의 step을 한 번에 조회
        steps = list(PipelineStep.objects.filter(pipeline=pipeline))
        existing_ids = {step.id for step in steps}

        # 요청 id와 실제 step id가 정확히 일치해야 한다
        if requested_ids != existing_ids:
            return Response(
                {"detail": "요청 id 목록이 파이프라인의 step과 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # id → step_order 매핑 생성
        order_map = {item["id"]: item["step_order"] for item in payload}

        with transaction.atomic():
            # unique_together 충돌 방지: 먼저 큰 임시 값으로 변경 후 최종 값 적용
            offset = PipelineStep.objects.filter(pipeline=pipeline).count() + 1000
            for step in steps:
                step.step_order = offset + step.id
            PipelineStep.objects.bulk_update(steps, ["step_order"])

            for step in steps:
                step.step_order = order_map[step.id]
            PipelineStep.objects.bulk_update(steps, ["step_order"])

        steps.sort(key=lambda s: s.step_order)
        serializer = PipelineStepSerializer(steps, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PipelineRunListView(ListAPIView):
    """
    GET /api/v1/pipelines/{pipeline_pk}/runs/ — 최신순 20건 반환
    타인 파이프라인의 run은 쿼리셋에서 제외되어 빈 배열로 응답한다.
    """

    serializer_class = PipelineRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # pipeline__owner 조건으로 소유권 검증 — 타인 접근 시 빈 쿼리셋 반환
        return PipelineRun.objects.filter(
            pipeline_id=self.kwargs["pipeline_pk"],
            pipeline__owner=self.request.user,
        )[:20]
