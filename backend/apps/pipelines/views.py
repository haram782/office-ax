from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Pipeline
from .serializers import PipelineSerializer


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
