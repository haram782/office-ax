"""
PII 마스킹 함수 검증 스크립트.
실행: cd ax-engine && .venv/bin/python tests/test_pii_masker.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from masking.pii_masker import mask_pii

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"


def check(name: str, text: str, expect_label: str, expect_original_absent: bool = True):
    masked, counts = mask_pii(text)
    label_present = expect_label in masked
    original_absent = expect_original_absent and (text == masked or expect_label in masked)

    ok = label_present and (expect_label in counts or any(expect_label in k for k in counts))
    print(f"  {'[PASS]' if ok else '[FAIL]'}  {name}")
    print(f"         입력  : {text.strip()}")
    print(f"         결과  : {masked.strip()}")
    print(f"         카운트: {counts}\n")
    return ok


def run():
    results = []

    print("=" * 55)
    print("  Office-AX PII Masker 검증")
    print("=" * 55 + "\n")

    # 1. 주민등록번호
    results.append(check(
        "주민등록번호 (생년월일-성별포함)",
        "고객 주민번호: 901225-1234567",
        "[REDACTED_ID]",
    ))

    # 2. 한국 계좌번호
    results.append(check(
        "계좌번호 (하이픈 포함)",
        "입금 계좌: 110-123456-12345",
        "[REDACTED_ACCOUNT]",
    ))

    # 3. 이메일
    results.append(check(
        "이메일 주소",
        "담당자: manager@company.co.kr",
        "[REDACTED_EMAIL]",
    ))

    # 4. 휴대폰 (010)
    results.append(check(
        "휴대폰 번호 (010)",
        "연락처: 010-1234-5678",
        "[REDACTED_PHONE]",
    ))

    # 5. 지역 전화번호 (02)
    results.append(check(
        "지역번호 전화 (02)",
        "사무실: 02-123-4567",
        "[REDACTED_PHONE]",
    ))

    # 6. 복합 — 여러 PII가 한 문장에
    text_multi = "고객: 홍길동, 주민번호 850101-1234567, 연락처 010-9876-5432, 이메일 hong@test.com"
    masked, counts = mask_pii(text_multi)
    ok = (
        "[REDACTED_ID]" in masked
        and "[REDACTED_PHONE]" in masked
        and "[REDACTED_EMAIL]" in masked
        and "850101-1234567" not in masked
        and "010-9876-5432" not in masked
        and "hong@test.com" not in masked
    )
    results.append(ok)
    print(f"  {'[PASS]' if ok else '[FAIL]'}  복합 PII (주민번호 + 전화 + 이메일 동시)")
    print(f"         입력  : {text_multi}")
    print(f"         결과  : {masked}")
    print(f"         카운트: {counts}\n")

    # 7. PII 없는 일반 텍스트 — 마스킹 없어야 함
    text_clean = "2024년 1월 매출: 1,200,000원, 영업이익률 12.5%"
    masked_clean, counts_clean = mask_pii(text_clean)
    ok_clean = masked_clean == text_clean and counts_clean == {}
    results.append(ok_clean)
    print(f"  {'[PASS]' if ok_clean else '[FAIL]'}  일반 텍스트 (마스킹 없어야 함)")
    print(f"         입력  : {text_clean}")
    print(f"         결과  : {masked_clean}")
    print(f"         카운트: {counts_clean}\n")

    print("=" * 55)
    passed = sum(results)
    total = len(results)
    status = "\033[92m전체 통과\033[0m" if passed == total else "\033[91m일부 실패\033[0m"
    print(f"  결과: {passed}/{total} — {status}")
    print("=" * 55)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    run()
