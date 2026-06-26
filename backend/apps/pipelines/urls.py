from django.urls import include, path

from .views import (
    PipelineDetailView,
    PipelineListCreateView,
    PipelineRunListView,
    StepDetailView,
    StepListCreateView,
    StepReorderView,
)

# steps 하위 URL 패턴 — /pipelines/{pipeline_pk}/steps/ 아래에 include된다
steps_patterns = [
    path("", StepListCreateView.as_view(), name="step-list"),
    path("<int:pk>/", StepDetailView.as_view(), name="step-detail"),
    path("reorder/", StepReorderView.as_view(), name="step-reorder"),
]

urlpatterns = [
    path("pipelines/", PipelineListCreateView.as_view(), name="pipeline-list"),
    path("pipelines/<int:pk>/", PipelineDetailView.as_view(), name="pipeline-detail"),
    path("pipelines/<int:pipeline_pk>/steps/", include(steps_patterns)),
    path("pipelines/<int:pipeline_pk>/runs/", PipelineRunListView.as_view(), name="pipeline-run-list"),
]
