from django.urls import path

from .views import GoogleAuthView, MeView

urlpatterns = [
    path("auth/google/", GoogleAuthView.as_view(), name="auth-google"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
]
