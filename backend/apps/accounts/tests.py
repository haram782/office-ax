"""
Google OAuth 인증 API 테스트.

커버 범위:
  1. POST /api/v1/auth/google/ — 정상 토큰으로 DRF 토큰 발급
  2. access_token 누락 시 400
  3. Google API 응답 실패 시 401
  4. verified_email=False 시 401
  5. 동일 이메일 재로그인 시 기존 유저 재사용 (get_or_create)
  6. GET /api/v1/auth/me/ — 인증된 사용자 정보 반환
  7. me/ 인증 없이 접근 시 401
  8. [회귀] username=email 이미 존재하는 유저에 잘못 매핑되지 않는다 (email 필드 기준 조회)
  9. [회귀] email 중복 유저 존재 시 MultipleObjectsReturned 방어 처리
  10. [회귀] 기존 유저의 first_name이 비어 있으면 Google name으로 업데이트
"""
import os
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()

# Google userinfo API 정상 응답 픽스처
_GOOGLE_USERINFO_OK = {
    "id": "123456789",
    "email": "tester@example.com",
    "verified_email": True,
    "name": "홍길동",
    "given_name": "길동",
    "family_name": "홍",
    "picture": "https://lh3.googleusercontent.com/photo.jpg",
}


def _mock_google_ok(payload=None):
    """Google userinfo API 성공 응답 목"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload or _GOOGLE_USERINFO_OK
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class GoogleAuthViewTest(TestCase):
    """POST /api/v1/auth/google/ 테스트."""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/google/"

    def test_valid_token_returns_drf_token(self):
        """정상 access_token으로 DRF 토큰과 user 정보를 반환한다."""
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok()):
            response = self.client.post(self.url, {"access_token": "valid-token"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "tester@example.com")
        self.assertEqual(response.data["user"]["name"], "홍길동")
        self.assertIn("picture", response.data["user"])
        self.assertIn("id", response.data["user"])
        self.assertIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["sessionid"]["secure"])
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(response.cookies["sessionid"]["samesite"], "Lax")

    def test_missing_access_token_returns_400(self):
        """access_token 필드 없이 요청하면 400 반환."""
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_empty_access_token_returns_400(self):
        """access_token이 빈 문자열이면 400 반환."""
        response = self.client.post(self.url, {"access_token": ""}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_google_api_network_error_returns_401(self):
        """Google API 네트워크 오류(예외 발생) 시 401 반환."""
        with patch("apps.accounts.views.requests.get", side_effect=Exception("timeout")):
            response = self.client.post(self.url, {"access_token": "bad-token"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_google_api_error_status_returns_401(self):
        """Google API가 4xx/5xx를 반환하면 401 반환."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        with patch("apps.accounts.views.requests.get", return_value=mock_resp):
            response = self.client.post(self.url, {"access_token": "expired-token"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_unverified_email_returns_401(self):
        """verified_email=False인 Google 계정은 401 반환."""
        payload = {**_GOOGLE_USERINFO_OK, "verified_email": False}
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok(payload)):
            response = self.client.post(self.url, {"access_token": "unverified-token"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_second_login_reuses_existing_user(self):
        """동일 이메일로 재로그인 시 유저가 새로 생성되지 않고 기존 유저를 재사용."""
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok()):
            self.client.post(self.url, {"access_token": "token-1"}, format="json")
        user_count_after_first = User.objects.filter(username="tester@example.com").count()

        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok()):
            self.client.post(self.url, {"access_token": "token-2"}, format="json")
        user_count_after_second = User.objects.filter(username="tester@example.com").count()

        self.assertEqual(user_count_after_first, 1)
        self.assertEqual(user_count_after_second, 1)

    def test_drf_token_consistent_across_logins(self):
        """동일 유저 재로그인 시 동일한 DRF 토큰을 반환한다."""
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok()):
            r1 = self.client.post(self.url, {"access_token": "token-a"}, format="json")
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok()):
            r2 = self.client.post(self.url, {"access_token": "token-b"}, format="json")

        self.assertEqual(r1.data["token"], r2.data["token"])


class BetaAllowlistTest(TestCase):
    """
    클로즈드 베타 이메일 allowlist 테스트.

    BETA_ALLOWED_EMAILS 환경변수(콤마 구분 목록)가 설정되면
    목록에 없는 이메일의 Google OAuth 로그인을 403으로 거부한다.
    미설정 시에는 기존 동작(전체 허용)을 유지한다.
    상세: docs/product/strategy/closed-beta-launch-plan-v1-ko.md 2.2절 결정 17
    """

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/google/"

    def _login(self, email="tester@example.com"):
        payload = {**_GOOGLE_USERINFO_OK, "email": email}
        with patch("apps.accounts.views.requests.get", return_value=_mock_google_ok(payload)):
            return self.client.post(self.url, {"access_token": "tok"}, format="json")

    def test_unlisted_email_returns_403(self):
        """allowlist에 없는 이메일은 403으로 거부한다."""
        with patch.dict(os.environ, {"BETA_ALLOWED_EMAILS": "invited@example.com"}):
            response = self._login(email="stranger@example.com")
        self.assertEqual(response.status_code, 403)

    def test_unlisted_email_does_not_create_user(self):
        """거부된 로그인 시도는 유저 레코드를 생성하지 않아야 한다."""
        with patch.dict(os.environ, {"BETA_ALLOWED_EMAILS": "invited@example.com"}):
            self._login(email="stranger@example.com")
        self.assertFalse(User.objects.filter(email="stranger@example.com").exists())

    def test_listed_email_returns_200(self):
        """allowlist에 있는 이메일은 정상 로그인된다."""
        with patch.dict(os.environ, {"BETA_ALLOWED_EMAILS": "invited@example.com,tester@example.com"}):
            response = self._login(email="tester@example.com")
        self.assertEqual(response.status_code, 200)

    def test_allowlist_is_case_and_space_insensitive(self):
        """대소문자·공백 차이는 무시하고 매칭한다 (경계 케이스)."""
        with patch.dict(os.environ, {"BETA_ALLOWED_EMAILS": " Invited@Example.com , Tester@EXAMPLE.com "}):
            response = self._login(email="tester@example.com")
        self.assertEqual(response.status_code, 200)

    def test_unset_allowlist_allows_all(self):
        """[회귀] 환경변수 미설정 시 기존 전체 허용 동작을 유지한다."""
        env = {k: v for k, v in os.environ.items() if k != "BETA_ALLOWED_EMAILS"}
        with patch.dict(os.environ, env, clear=True):
            response = self._login(email="anyone@example.com")
        self.assertEqual(response.status_code, 200)

    def test_empty_allowlist_allows_all(self):
        """[경계] 환경변수가 빈 문자열이면 전체 허용으로 취급한다."""
        with patch.dict(os.environ, {"BETA_ALLOWED_EMAILS": "  "}):
            response = self._login(email="anyone@example.com")
        self.assertEqual(response.status_code, 200)

    def test_open_access_mode_allows_all_even_with_stale_allowlist(self):
        """open 모드는 이전 allowlist 값이 남아 있어도 인증 계정을 모두 허용한다."""
        with patch.dict(
            os.environ,
            {"BETA_ACCESS_MODE": "open", "BETA_ALLOWED_EMAILS": "invited@example.com"},
        ):
            response = self._login(email="anyone@example.com")
        self.assertEqual(response.status_code, 200)

    def test_explicit_allowlist_mode_fails_closed_when_list_is_empty(self):
        """allowlist 모드에서 목록 누락은 전체 공개가 아니라 접근 거부로 처리한다."""
        with patch.dict(
            os.environ,
            {"BETA_ACCESS_MODE": "allowlist", "BETA_ALLOWED_EMAILS": ""},
        ):
            response = self._login(email="anyone@example.com")
        self.assertEqual(response.status_code, 403)

    def test_unknown_access_mode_fails_closed(self):
        """오타 난 접근 모드는 preflight 우회 시에도 전체 공개되지 않는다."""
        with patch.dict(
            os.environ,
            {"BETA_ACCESS_MODE": "typo", "BETA_ALLOWED_EMAILS": ""},
        ):
            response = self._login(email="anyone@example.com")
        self.assertEqual(response.status_code, 403)


class MeViewTest(TestCase):
    """GET /api/v1/auth/me/ 테스트."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="me@example.com",
            email="me@example.com",
            first_name="미",
            last_name="유저",
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_returns_user_info(self):
        """인증된 사용자 정보(id, email, name)를 반환한다."""
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "me@example.com")
        self.assertIn("id", response.data)
        self.assertIn("name", response.data)

    def test_unauthenticated_returns_401(self):
        """인증 헤더 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)


class LogoutViewTest(TestCase):
    def test_logout_revokes_token_and_session(self):
        user = User.objects.create_user(username="logout", password="pw")
        token = Token.objects.create(user=user)
        client = APIClient()
        client.force_login(user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertNotIn("_auth_user_id", client.session)


class GoogleAuthUserMappingRegressionTest(TestCase):
    """
    username=email 기존 유저에 잘못 매핑되는 버그 회귀 테스트.
    조회 기준을 email 필드로 변경했을 때의 동작을 검증한다.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/google/"

    def _login_google(self, email="tester@example.com", name="홍길동"):
        payload = {
            "id": "999", "email": email, "verified_email": True,
            "name": name, "given_name": "길동", "family_name": "홍",
            "picture": "https://photo.jpg",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch("apps.accounts.views.requests.get", return_value=mock_resp):
            return self.client.post(self.url, {"access_token": "tok"}, format="json")

    def test_existing_username_email_user_not_hijacked(self):
        """
        [회귀] username=email 형태로 미리 등록된 superuser/테스트 유저가 있어도
        Google OAuth 로그인 시 해당 유저에 매핑되지 않고 신규 유저를 생성해야 한다.
        조회 키가 username → email로 변경됐을 때의 핵심 동작 검증.
        """
        # username=email 기존 유저 생성 (email 필드는 다른 값)
        existing = User.objects.create_user(
            username="tester@example.com",
            email="other@internal.com",  # email 필드가 다름
            password="pw",
        )
        existing_session_count = existing.chat_sessions.count()  # 0

        response = self._login_google(email="tester@example.com")
        self.assertEqual(response.status_code, 200)

        # OAuth로 로그인된 유저 ID가 기존 유저와 달라야 한다
        oauth_user_id = response.data["user"]["id"]
        self.assertNotEqual(
            oauth_user_id, existing.pk,
            "username=email 기존 유저에 잘못 매핑됐습니다 (버그 재현)",
        )

    def test_same_email_reuses_oauth_user(self):
        """동일 email로 두 번 OAuth 로그인 시 유저가 하나만 존재해야 한다."""
        self._login_google()
        self._login_google()
        count = User.objects.filter(email="tester@example.com").count()
        self.assertEqual(count, 1)

    def test_multiple_objects_returned_uses_first(self):
        """
        [방어] email 중복 유저가 DB에 있으면 MultipleObjectsReturned를 처리하고
        id 기준 첫 번째 유저를 반환한다.
        """
        # email이 동일한 유저 두 명을 강제로 생성
        u1 = User.objects.create_user(username="dup1", email="dup@example.com")
        u2 = User.objects.create_user(username="dup2", email="dup@example.com")

        payload = {
            "id": "777", "email": "dup@example.com", "verified_email": True,
            "name": "중복유저", "given_name": "", "family_name": "",
            "picture": "",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch("apps.accounts.views.requests.get", return_value=mock_resp):
            response = self.client.post(self.url, {"access_token": "tok"}, format="json")

        self.assertEqual(response.status_code, 200)
        # id 오름차순 첫 번째 유저여야 한다
        self.assertEqual(response.data["user"]["id"], u1.pk)

    def test_existing_user_without_first_name_gets_updated(self):
        """
        [회귀] email 기준으로 조회된 기존 유저의 first_name이 비어 있으면
        Google name 값으로 업데이트해야 한다.
        """
        # first_name 없이 미리 등록된 유저
        existing = User.objects.create_user(
            username="noname@example.com",
            email="noname@example.com",
            first_name="",
        )

        payload = {
            "id": "888", "email": "noname@example.com", "verified_email": True,
            "name": "이름업데이트", "given_name": "업데이트", "family_name": "이름",
            "picture": "",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch("apps.accounts.views.requests.get", return_value=mock_resp):
            self.client.post(self.url, {"access_token": "tok"}, format="json")

        existing.refresh_from_db()
        self.assertEqual(existing.first_name, "이름업데이트")
