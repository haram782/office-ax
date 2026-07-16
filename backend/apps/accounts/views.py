import os
import uuid

import requests

from django.contrib.auth import get_user_model, login, logout
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()

# Google OAuth userinfo 엔드포인트
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"


def _is_beta_allowed(email: str) -> bool:
    """
    클로즈드 베타 이메일 allowlist 검사.

    BETA_ACCESS_MODE=open이면 인증된 Google 계정을 모두 허용하고,
    allowlist이면 BETA_ALLOWED_EMAILS에 있는 계정만 허용한다.
    BETA_ACCESS_MODE가 없으면 기존의 빈 목록 전체 허용 동작을 유지한다.
    요청 시점마다 읽으므로 재배포 없이 프로세스 재시작만으로 명단 갱신 가능.
    상세: docs/product/strategy/closed-beta-launch-plan-v1-ko.md 2.2절 결정 17
    """
    mode = os.environ.get("BETA_ACCESS_MODE", "").strip().lower()
    raw = os.environ.get("BETA_ALLOWED_EMAILS", "").strip()
    if mode == "open":
        return True
    if mode not in {"", "allowlist"}:
        return False
    if mode == "allowlist" and not raw:
        return False
    if not raw:
        return True
    allowed = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return email.strip().lower() in allowed


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

        # 클로즈드 베타 allowlist — 유저 생성 전에 차단해야 레코드가 남지 않는다
        if not _is_beta_allowed(email):
            return Response(
                {"error": "클로즈드 베타 초대 대상이 아닙니다. 초대를 원하시면 운영자에게 문의해주세요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # email 필드 기준으로 유저 조회.
        # username 기준 조회 시 username=email 형태의 기존 슈퍼유저·테스트 유저에
        # 잘못 매핑되어 해당 유저의 세션 전체가 노출되는 버그가 발생한다.
        # Django 기본 User의 email은 unique 제약이 없으므로 중복이 생길 수 있다.
        user = User.objects.filter(email=email).order_by("id").first()
        created = user is None

        if created:
            # username unique 제약 방어: 동일 username이 이미 있으면 uuid suffix 추가
            username = email
            if User.objects.filter(username=username).exists():
                username = f"{email[:143]}_{uuid.uuid4().hex[:6]}"
            user = User.objects.create_user(
                username=username, email=email, first_name=name
            )
        elif not user.first_name and name:
            # 기존 유저인데 이름 정보가 없으면 Google 이름으로 채워 준다
            user.first_name = name
            user.save(update_fields=["first_name"])

        # DRF 토큰 조회 또는 생성 — 재로그인 시 동일 토큰 유지
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

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


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — API token과 media session을 함께 종료한다."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
