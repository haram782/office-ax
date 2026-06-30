# Patch Plan JSON 스키마

## 개요

LLM이 생성한 문서 수정 계획(patch plan)의 JSON 구조를 정의한다.
백엔드 `DocumentVersion.patch_plan` 필드에 저장되며,
patcher가 실제 파일을 수정할 때 이 스키마를 입력으로 사용한다.

---

## 최상위 구조

```json
{
  "version": "1.0",
  "items": [ <PatchItem>, ... ]
}
```

---

## PatchItem 필드

| 필드          | 타입              | 필수 | 설명                                              |
|---------------|-------------------|------|---------------------------------------------------|
| `change_id`   | string (UUID v4)  | ✅   | 변경 항목 고유 식별자. `DocumentChange.change_id`와 1:1 매핑 |
| `format`      | string (enum)     | ✅   | 대상 파일 포맷. 아래 허용값 참조                   |
| `operation`   | string (enum)     | ✅   | 수정 방식. 포맷별 허용 operation 테이블 참조        |
| `original`    | string            | ✅   | 원본 텍스트 또는 셀 값                             |
| `replacement` | string            | ✅   | 교체할 텍스트 또는 셀 값                           |
| `reason`      | string            | ✅   | LLM이 생성한 변경 이유 (한국어 권장)               |
| `confidence`  | float (0.0–1.0)   | ✅   | LLM의 변경 신뢰도. 1.0에 가까울수록 확실           |
| `anchor`      | object            | ✅   | 포맷별 위치 정보. 아래 anchor 스키마 참조           |
| `status`      | string (enum)     | ✅   | 변경 항목 처리 상태. 아래 허용값 참조               |

### format 허용값

| 값       | 설명                          |
|----------|-------------------------------|
| `excel`  | Microsoft Excel (.xlsx)       |
| `docx`   | Microsoft Word (.docx)        |
| `hwp`    | 한글 (.hwp)                   |
| `hwpx`   | 한글 XML (.hwpx)              |
| `pptx`   | Microsoft PowerPoint (.pptx)  |
| `pdf`    | PDF                           |
| `csv`    | CSV (쉼표 구분 텍스트)         |

### status 허용값

| 값          | 설명                                      |
|-------------|-------------------------------------------|
| `pending`   | 사용자 검토 대기 중 (기본값)              |
| `accepted`  | 사용자가 적용 승인 (아직 파일 미반영)     |
| `rejected`  | 사용자가 거부                             |
| `applied`   | patcher가 파일에 실제 반영 완료           |
| `failed`    | patcher 적용 중 오류 발생                 |

---

## operation 값과 포맷별 매핑

| operation         | 지원 포맷              | 동작 설명                                                        |
|-------------------|------------------------|------------------------------------------------------------------|
| `replace_text`    | HWP, HWPX, DOCX        | 텍스트 검색 후 치환. `anchor.type`은 `text_match` 사용           |
| `replace_cell`    | Excel, CSV             | 셀 좌표 기반 값 교체. `anchor.type`은 `cell` 사용               |
| `annotate`        | PDF                    | 원본을 수정하지 않고 highlight annotation 추가                   |
| `redact_overlay`  | PDF                    | 기존 텍스트를 불투명 박스로 가리고 새 텍스트를 오버레이          |
| `regenerate`      | PDF                    | 원본 내용 추출 후 새 PDF로 재생성 (대규모 구조 변경 시 사용)    |
| `replace_shape`   | PPTX                   | 슬라이드 내 셰이프의 텍스트 교체. `anchor.type`은 `slide_shape` |

> **제약**: 포맷과 operation의 조합이 위 테이블에 없으면 patcher가 거부한다.

---

## anchor 스키마

### cell anchor (Excel / CSV)

```json
{
  "type": "cell",
  "sheet": "Sheet1",
  "cell": "D12"
}
```

| 필드    | 타입   | 필수 | 설명                                      |
|---------|--------|------|-------------------------------------------|
| `type`  | string | ✅   | 고정값 `"cell"`                           |
| `sheet` | string | ❌   | 시트 이름. Excel 전용. CSV는 생략         |
| `cell`  | string | ✅   | A1 표기법 셀 좌표 (예: `"D12"`, `"B3"`) |

### text_match anchor (HWP / HWPX / DOCX)

```json
{
  "type": "text_match",
  "target_text": "계약금액 일금오백만원",
  "context_before": "제3조(계약금액)",
  "context_after": "정(整)으로 한다."
}
```

| 필드             | 타입   | 필수 | 설명                                         |
|------------------|--------|------|----------------------------------------------|
| `type`           | string | ✅   | 고정값 `"text_match"`                        |
| `target_text`    | string | ✅   | 검색할 원본 텍스트 (exact match 우선 시도)   |
| `context_before` | string | ❌   | 앞 문맥 (동일 문자열이 여러 개일 때 구분 용) |
| `context_after`  | string | ❌   | 뒤 문맥                                      |

### slide_shape anchor (PPTX)

```json
{
  "type": "slide_shape",
  "slide_index": 2,
  "shape_id": 5,
  "shape_name": "Title 1"
}
```

| 필드          | 타입    | 필수 | 설명                                              |
|---------------|---------|------|---------------------------------------------------|
| `type`        | string  | ✅   | 고정값 `"slide_shape"`                            |
| `slide_index` | integer | ✅   | 0-based 슬라이드 인덱스                           |
| `shape_id`    | integer | ❌   | python-pptx shape.shape_id. 없으면 이름으로 탐색 |
| `shape_name`  | string  | ❌   | shape.name. shape_id와 중 하나는 필수             |

### pdf_region anchor (PDF)

```json
{
  "type": "pdf_region",
  "page": 0,
  "bbox": [72.0, 100.0, 400.0, 120.0]
}
```

| 필드   | 타입             | 필수 | 설명                                              |
|--------|------------------|------|---------------------------------------------------|
| `type` | string           | ✅   | 고정값 `"pdf_region"`                             |
| `page` | integer          | ✅   | 0-based 페이지 번호                               |
| `bbox` | [x0,y0,x1,y1]   | ❌   | PDF 좌표계 기준 영역. `annotate`/`redact_overlay` 시 권장 |

---

## 전체 예시

```json
{
  "version": "1.0",
  "items": [
    {
      "change_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
      "format": "excel",
      "operation": "replace_cell",
      "original": "5,000,000",
      "replacement": "6,500,000",
      "reason": "2025년 단가 인상분 반영 (30% 상승)",
      "confidence": 0.95,
      "anchor": {
        "type": "cell",
        "sheet": "정산내역",
        "cell": "D12"
      },
      "status": "pending"
    },
    {
      "change_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "format": "docx",
      "operation": "replace_text",
      "original": "계약금액 일금오백만원",
      "replacement": "계약금액 일금육백오십만원",
      "reason": "단가 인상분에 따른 계약금액 수정",
      "confidence": 0.91,
      "anchor": {
        "type": "text_match",
        "target_text": "계약금액 일금오백만원",
        "context_before": "제3조(계약금액)",
        "context_after": "정(整)으로 한다."
      },
      "status": "pending"
    },
    {
      "change_id": "550e8400-e29b-41d4-a716-446655440000",
      "format": "pdf",
      "operation": "annotate",
      "original": "연간 유지보수 비용: 500,000원",
      "replacement": "연간 유지보수 비용: 650,000원",
      "reason": "단가 인상분 검토 필요 항목 표시",
      "confidence": 0.78,
      "anchor": {
        "type": "pdf_region",
        "page": 2,
        "bbox": [72.0, 310.5, 380.0, 325.0]
      },
      "status": "pending"
    }
  ]
}
```

---

## 버전 이력

| 버전  | 날짜       | 변경 내용                          |
|-------|------------|------------------------------------|
| 1.0   | 2026-06-28 | 초안 작성. 6개 포맷, 6개 operation |
