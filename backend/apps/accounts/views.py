import requests

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()

# Google OAuth userinfo 엔드포인트
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"


class GoogleAuthView(APIView):
    """
    POST /api/v1/auth/google/
    Google OAuth access_token을 검증하고 DRF 토큰을 발급한다.
    """

    # 전역 IsAuthenticated를 오버라이드 — 로그인 전 접근이므로 AllowAny 필요
    permission_classes = [AllowAny]

    def post(self, request):
        access_token = request.data.get("access_token", "").strip()
        if not access_token:
            return Response(
                {"error": "access_token이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Google userinfo API 호출 — 네트워크/외부 API 실패는 인프라 예외로 처리
        try:
            resp = requests.get(
                _GOOGLE_USERINFO_URL,
                params={"access_token": access_token},
                timeout=5,
            )
            resp.raise_for_status()
            userinfo = resp.json()
        except Exception:
            return Response(
                {"error": "Google 토큰 검증에 실패했습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not userinfo.get("verified_email"):
            return Response(
                {"error": "이메일이 인증되지 않은 Google 계정입니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        email   = userinfo.get("email", "")
        # Google name 필드를 그대로 사용 — 언어·문화권별 순서 차이를 보존
        name    = userinfo.get("name", "")
        picture = userinfo.get("picture", "")

        # 이메일 기반으로 유저 조회 또는 생성
        # first_name에 전체 이름을 저장해 me/ API에서도 일관 반환
        user, _ = User.objects.get_or_create(
            username=email,
            defaults={"email": email, "first_name": name},
        )

        # DRF 토큰 조회 또는 생성 — 재로그인 시 동일 토큰 유지
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user": {
                "id":      user.pk,
                "email":   user.email,
                "name":    name or email,
                "picture": picture,
            },
        })


class MeView(APIView):
    """GET /api/v1/auth/me/ — 현재 로그인한 유저 정보 반환."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # first_name에 Google name 전체가 저장되므로 그대로 사용
        name = user.first_name or user.username
        return Response({
            "id":    user.pk,
            "email": user.email,
            "name":  name,
        })
