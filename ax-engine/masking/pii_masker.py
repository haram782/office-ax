import re

# (컴파일된 패턴, 치환 레이블) 순서가 중요하다.
# 주민번호 패턴이 전화번호 패턴보다 먼저 와야 오탐을 줄일 수 있다.
_RULES: list[tuple[re.Pattern, str]] = [
    (
        # 주민등록번호: 계좌/전화 패턴보다 먼저 검사해야 오탐을 줄일 수 있다.
        re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
        "[REDACTED_ID]",
    ),
    (
        # 전화번호를 계좌번호보다 먼저 검사: 010-1234-5678 이 계좌 패턴에 오탐되는 것을 방지.
        # 휴대폰(010-XXXX-XXXX), 일반전화(02-XXX-XXXX), 지역번호(0XX-XXX-XXXX)
        re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}"),
        "[REDACTED_PHONE]",
    ),
    (
        # 한국 계좌번호: 은행별로 10~14자리, 하이픈 구분. 전화번호 마스킹 후 검사.
        re.compile(r"\b\d{3,4}-\d{4,6}-\d{4,6}(?:-\d{2})?\b"),
        "[REDACTED_ACCOUNT]",
    ),
    (
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        "[REDACTED_EMAIL]",
    ),
]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """
    Returns (masked_text, {label: count}).
    count는 Django 백엔드가 마스킹 감사 로그를 기록할 때 활용한다.
    """
    counts: dict[str, int] = {}

    for pattern, label in _RULES:
        matches = pattern.findall(text)
        if matches:
            counts[label] = counts.get(label, 0) + len(matches)
        text = pattern.sub(label, text)

    return text, counts
