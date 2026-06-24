from celery import current_app
from rest_framework import status
from rest_framework.generics import DestroyAPIView, ListCreateAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RagAsset
from .serializers import RagAssetSerializer


class RagAssetListCreateView(ListCreateAPIView):
    """
    GET  /api/v1/rag-assets/ — 본인 RAG 자산 목록
    POST /api/v1/rag-assets/ — 파일 업로드로 자산 생성 + 학습 태스크 예약
    """

    serializer_class = RagAssetSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return RagAsset.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        file_obj = self.request.FILES.get("file")
        file_size = file_obj.size if file_obj else 0

        asset = serializer.save(owner=self.request.user, file_size=file_size)

        # 업로드 완료 후 비동기 학습 태스크를 예약
        # 문자열 기반 send_task로 Django ↔ Celery 물리적 결합 방지
        current_app.send_task(
            "rag.train_asset",
            kwargs={"asset_id": asset.pk},
        )


class RagAssetFileUrlView(APIView):
    """
    GET /api/v1/rag-assets/:id/file/
    RAG 자산 파일의 다운로드 URL을 반환한다.
    본인 소유 자산만 접근 가능 — 타인 접근 시 404.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        try:
            asset = RagAsset.objects.get(pk=pk, owner=request.user)
        except RagAsset.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response({
            "file_url": asset.file.url if asset.file else "",
            "group_name": asset.group_name,
            "kind": asset.kind,
        })


class RagAssetDestroyView(DestroyAPIView):
    """DELETE /api/v1/rag-assets/{id}/ — 본인 자산 삭제"""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 본인 소유 자산만 삭제 가능 — 타인 접근 시 404
        return RagAsset.objects.filter(owner=self.request.user)
