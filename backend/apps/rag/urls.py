from django.urls import path

from .views import RagAssetDestroyView, RagAssetFileUrlView, RagAssetListCreateView

urlpatterns = [
    path("rag-assets/", RagAssetListCreateView.as_view(), name="rag-asset-list"),
    path("rag-assets/<int:pk>/", RagAssetDestroyView.as_view(), name="rag-asset-destroy"),
    path("rag-assets/<int:pk>/file/", RagAssetFileUrlView.as_view(), name="rag-asset-file"),
]
