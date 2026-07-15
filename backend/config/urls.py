from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.documents.media import protected_media
from config.health import liveness, readiness

urlpatterns = [
    path("healthz", liveness, name="healthz"),
    path("readyz", readiness, name="readyz"),
    path("media/<path:path>", protected_media, name="protected-media"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.documents.urls")),
    path("api/v1/chat/", include("apps.chat.urls")),
    path("api/v1/", include("apps.chat.urls_conversations")),
    path("api/v1/", include("apps.pipelines.urls")),
    path("api/v1/", include("apps.rag.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
