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


def mask_pii(text: str) -> tuple[str, dict[str, int], dict[str, list[str]]]:
    """
    Returns (masked_text, {label: count}, {label: [원본값, ...]}).
    count는 Django 백엔드가 마스킹 감사 로그를 기록할 때 활용한다.
    mapping은 발견 순서대로 원본값을 담아 unmask_pii로 복원할 때 쓴다
    (예: text_chat 의도 판별 단계에서 마스킹한 값을 PatchPlan 생성 직전에
    되돌리는 용도 — closed-beta-launch-plan-v1-ko.md 결정 11).
    """
    counts: dict[str, int] = {}
    mapping: dict[str, list[str]] = {}

    for pattern, label in _RULES:
        matches = pattern.findall(text)
        if matches:
            counts[label] = counts.get(label, 0) + len(matches)
            mapping.setdefault(label, []).extend(matches)
        text = pattern.sub(label, text)

    return text, counts, mapping


def unmask_pii(text: str, mapping: dict[str, list[str]]) -> str:
    """
    mask_pii가 반환한 mapping으로 자리표시자를 원본값으로 되돌린다.
    같은 라벨이 여러 번 나오면 마스킹 시 발견된 순서대로 하나씩 복원한다.
    """
    for label, originals in mapping.items():
        for original in originals:
            text = text.replace(label, original, 1)
    return text
