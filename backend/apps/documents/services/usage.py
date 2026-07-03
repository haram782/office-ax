from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth import get_user_model

from apps.documents.models import DocumentVersion, UploadLog, UsageEvent
from apps.documents.services.pricing import estimate_cost_krw

logger = logging.getLogger(__name__)

User = get_user_model()


def record_usage_event(
    *,
    user: User,
    event_type: str,
    status: str = UsageEvent.Status.SUCCESS,
    upload_log: UploadLog | None = None,
    document_version: DocumentVersion | None = None,
    chat_session=None,
    provider: str = "",
    model: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    token_source: str | None = None,
    estimated_cost: Decimal | int | float | str | None = None,
    latency_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> UsageEvent | None:
    """
    사용량 이벤트를 best-effort로 기록한다.

    기록 실패는 원래 작업 흐름을 깨지 않도록 로그만 남기고 None을 반환한다.
    """
    try:
        usage = metadata.get("usage") if isinstance(metadata, dict) else None
        input_value = _coerce_int(
            input_tokens,
            _lookup(usage, "input_tokens", "prompt_tokens", "input"),
        )
        output_value = _coerce_int(
            output_tokens,
            _lookup(usage, "output_tokens", "completion_tokens", "output"),
        )
        source = token_source or _lookup(usage, "token_source")
        if not source:
            source = UsageEvent.TokenSource.PROVIDER_REPORTED if input_value or output_value else UsageEvent.TokenSource.UNAVAILABLE

        resolved_model = model or str(_lookup(metadata, "model") or _lookup(usage, "model") or "")
        cost_value = _coerce_optional_decimal(
            estimated_cost,
            _lookup(metadata, "estimated_cost") or _lookup(usage, "estimated_cost") or _lookup(usage, "cost"),
        )
        if cost_value is None:
            # 명시적 비용 정보가 없으면 pricing.py 가격표로 계산한 값을 스냅샷으로 저장한다.
            cost_value = estimate_cost_krw(resolved_model, input_value, output_value)

        return UsageEvent.objects.create(
            user=user,
            upload_log=upload_log,
            document_version=document_version,
            chat_session=chat_session,
            event_type=event_type,
            provider=provider or str(_lookup(metadata, "provider") or _lookup(usage, "provider") or ""),
            model=resolved_model,
            input_tokens=input_value,
            output_tokens=output_value,
            token_source=source,
            estimated_cost=cost_value,
            latency_ms=_coerce_optional_int(latency_ms, _lookup(metadata, "latency_ms") or _lookup(usage, "latency_ms")),
            status=status,
            metadata=metadata or {},
        )
    except Exception:
        logger.exception(
            "UsageEvent 기록 실패 | user_id=%s | event_type=%s | status=%s",
            getattr(user, "pk", None),
            event_type,
            status,
        )
        return None


def usage_metadata_from_result(result: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        result = {}
    metadata = {
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
        "usage": result.get("usage") or result.get("token_usage") or {},
        "latency_ms": result.get("latency_ms"),
        "estimated_cost": result.get("estimated_cost"),
    }
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def _lookup(source: Any, *keys: str) -> Any:
    if not isinstance(source, dict):
        return None
    for key in keys:
        if source.get(key) is not None:
            return source[key]
    return None


def _coerce_int(primary: Any, fallback: Any = None) -> int:
    value = primary if primary is not None else fallback
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _coerce_optional_int(primary: Any, fallback: Any = None) -> int | None:
    value = primary if primary is not None else fallback
    if value in (None, ""):
        return None
    return _coerce_int(value)


def _coerce_decimal(primary: Any, fallback: Any = None) -> Decimal:
    value = primary if primary is not None else fallback
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _coerce_optional_decimal(primary: Any, fallback: Any = None) -> Decimal | None:
    """
    명시적으로 전달된 비용 값이 없거나 파싱 불가능하면 None을 반환한다.
    호출 측은 None일 때 pricing.py 가격표로 비용을 다시 계산한다.
    """
    value = primary if primary is not None else fallback
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
