from django.urls import path

from .views import PipelineDetailView, PipelineListCreateView

urlpatterns = [
    path("pipelines/", PipelineListCreateView.as_view(), name="pipeline-list"),
    path("pipelines/<int:pk>/", PipelineDetailView.as_view(), name="pipeline-detail"),
]
