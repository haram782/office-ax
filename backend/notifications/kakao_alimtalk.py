"""
카카오 알림톡 발송 모듈 (Solapi REST API v4)

사전 준비:
  1. 솔라피(solapi.com) 계정 생성 후 API Key / Secret 발급
  2. 카카오 채널(플친) 개설 → pfId 확보
  3. 알림톡 템플릿 등록 후 카카오 검수 승인 → templateId 확보
  4. 발신번호 등록 (from_number)

템플릿 변수 예시:
  [Office-AX 분석 완료 알림]
  ───────────────────────
  서류명: #{서류명}

  분석 요약
  #{요약내용}

  감지된 오류: #{오류건수}건
  ───────────────────────
  자세한 결과는 Office-AX 대시보드에서 확인하세요.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_SOLAPI_SEND_URL = "https://api.solapi.com/messages/v4/send"
_REQUEST_TIMEOUT = 10  # seconds


@dataclass
class AlimtalkPayload:
    to: str           # 수신자 국내 휴대폰 번호 (하이픈 포함/미포함 모두 가능)
    doc_name: str     # #{서류명} 에 매핑
    summary: str      # #{요약내용} 에 매핑
    error_count: int = 0   # #{오류건수} 에 매핑


class AlimtalkError(Exception):
    """알림톡 발송 실패 시 래핑하는 예외. 상위에서 세분화 처리 가능."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def send_alimtalk(payload: AlimtalkPayload) -> dict:
    """
    Solapi REST API로 카카오 알림톡 단건 발송.

    Returns:
        Solapi API 성공 응답 dict

    Raises:
        AlimtalkError: 환경변수 누락, API 오류, 네트워크 타임아웃
    """
    _validate_env()

    api_key = os.environ["SOLAPI_API_KEY"]
    api_secret = os.environ["SOLAPI_API_SECRET"]

    body = _build_request_body(payload)
    headers = {
        "Content-Type": "application/json",
        "Authorization": _build_auth_header(api_key, api_secret),
    }

    try:
        response = requests.post(
            _SOLAPI_SEND_URL,
            json=body,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise AlimtalkError("Solapi 요청 타임아웃") from exc
    except requests.RequestException as exc:
        raise AlimtalkError(f"Solapi 네트워크 오류: {exc}") from exc

    if not response.ok:
        raise AlimtalkError(
            f"Solapi API 오류 [{response.status_code}]: {response.text}",
            status_code=response.status_code,
        )

    return response.json()


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _build_request_body(payload: AlimtalkPayload) -> dict:
    return {
        "message": {
            "to": _normalize_phone(payload.to),
            "from": os.environ["SOLAPI_FROM_NUMBER"],
            "kakaoOptions": {
                "pfId": os.environ["KAKAO_SENDER_PF_ID"],
                "templateId": os.environ["KAKAO_TEMPLATE_ID"],
                "variables": {
                    "#{서류명}": payload.doc_name[:40],      # 템플릿 최대 길이 방어
                    "#{요약내용}": payload.summary[:200],
                    "#{오류건수}": str(payload.error_count),
                },
            },
        }
    }


def _build_auth_header(api_key: str, api_secret: str) -> str:
    """
    Solapi HMAC-SHA256 인증 헤더.
    규격: HMAC-SHA256 apiKey={key}, date={iso8601}, salt={nonce}, signature={hmac}
    """
    date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    salt = uuid.uuid4().hex   # 32자 랜덤 nonce
    data = (date + salt).encode("utf-8")
    signature = hmac.new(
        api_secret.encode("utf-8"), data, hashlib.sha256
    ).hexdigest()
    return f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}"


def _normalize_phone(number: str) -> str:
    """'010-1234-5678' / '010 1234 5678' → '01012345678'"""
    return re.sub(r"[\s\-]", "", number)


def _validate_env() -> None:
    required = [
        "SOLAPI_API_KEY",
        "SOLAPI_API_SECRET",
        "SOLAPI_FROM_NUMBER",
        "KAKAO_SENDER_PF_ID",
        "KAKAO_TEMPLATE_ID",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise AlimtalkError(f"필수 환경변수 누락: {missing}")
