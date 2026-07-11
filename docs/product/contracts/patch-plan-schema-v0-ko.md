# Office-AX Patch Plan JSON 스키마 v0

문서 상태: 활성 계약 문서. LLM, 백엔드, patcher, 프론트가 공유하는 operation/anchor/patch payload를 바꿀 때 이 문서를 함께 갱신한다.

## 1. 목적

이 문서는 프롬프트 기반 문서 수정에서 LLM, 백엔드, 문서 patcher, 뷰어가 공유할 중간 계약을 정의한다.

핵심 원칙:

- 사용자는 뷰어에서 직접 편집하지 않는다.
- 사용자는 프롬프트로 문서 수정을 요청한다.
- LLM은 실제 파일을 수정하지 않고 구조화된 `PatchPlan`을 생성한다.
- 서버는 `PatchPlan`을 검증하고 `DocumentChange`로 저장한다.
- 문서 patcher는 승인된 변경만 실제 문서 버전에 반영한다.
- 결과 파일은 새 `DocumentVersion`과 artifact로 저장한다.

## 2. 용어

### PatchPlan

하나의 사용자 수정 요청에 대해 생성된 변경 계획 묶음.

예:

```text
"날짜 형식 통일하고 누락된 전화번호 표시해줘"
```

이 요청은 여러 개의 `PatchOperation`으로 분해될 수 있다.

### PatchOperation

실제 문서에 적용 가능한 최소 변경 단위.

예:

- 셀 값 변경
- 텍스트 치환
- PDF 주석 추가
- PDF redaction + overlay
- 문서 전체 재생성

### DocumentChange

`PatchOperation`을 서버 DB에 저장한 상태 객체.

프론트의 `suggestion`과 1:1 또는 1:N으로 연결될 수 있다.

### DocumentVersion

원본 또는 수정 결과 문서 버전.

예:

- v0 원본
- v1 날짜 형식 통일
- v2 개인정보 마스킹

### Artifact

문서 처리 결과 파일.

예:

- 수정본 `.xlsx`
- 수정본 `.hwp`
- 검토본 `.pdf`
- 재작성본 `.pdf`

## 3. 전체 흐름

```text
User prompt
  -> LLM generates PatchPlan
  -> Backend validates PatchPlan
  -> Backend stores DocumentChange rows
  -> Viewer shows suggestions
  -> User applies / rejects changes
  -> Patch job collects applied changes
  -> Patcher creates new file
  -> Backend stores DocumentVersion + artifact
  -> Viewer shows version history
```

## 4. Top-level PatchPlan

```json
{
  "schema": "office_ax.patch_plan.v0",
  "plan_id": "plan_20260628_001",
  "request": {
    "prompt": "날짜 형식 통일하고 누락된 전화번호 표시해줘",
    "mode": "edit_document"
  },
  "document": {
    "upload_id": 87,
    "base_version_id": "ver_000",
    "filename": "청약신청서 접수증.pdf",
    "format": "pdf",
    "source_type": "pdf_digital"
  },
  "strategy": {
    "kind": "patch",
    "requires_regeneration": false,
    "artifact_format": "pdf"
  },
  "summary": "날짜 표기와 누락 항목에 대한 수정 제안을 생성했습니다.",
  "operations": [],
  "warnings": [],
  "model": {
    "provider": "google",
    "model": "gemini-2.0-flash",
    "latency_ms": 0
  }
}
```

## 5. PatchOperation 공통 필드

```json
{
  "operation_id": "op_001",
  "suggestion_id": "sug_001",
  "format": "pdf",
  "operation": "annotate",
  "status": "pending",
  "severity": "warning",
  "title": "유선 전화번호 누락",
  "original": "",
  "replacement": "유선 전화번호 확인 필요",
  "reason": "신청자 인적사항에 유선 전화번호가 비어 있습니다.",
  "confidence": 0.91,
  "anchor": {},
  "patch": {},
  "risk": {
    "level": "low",
    "requires_user_confirmation": false,
    "notes": []
  }
}
```

### operation

초기 v0에서 허용하는 값:

```text
replace_text
replace_cell
annotate
redact_overlay
regenerate
```

v1에서 추가된 값 (XLSX 전용, 자세한 내용은 `../feature-specs/document-format-editing-ax-v1-ko.md` 6-7절 참조):

```text
set_cell_style
```

다음 구현 로드맵에서 추가된 값 (XLSX 전용, 자세한 내용은
`../roadmap/document-editing-ax-next-roadmap-v1-ko.md` 6.Phase2-3절 참조):

```text
set_number_format
set_formula
```

향후 후보:

```text
insert_text
delete_text
replace_shape_text
replace_table_cell
mask_pii
```

## 6. 포맷별 operation 의미

| operation | XLSX | HWP/HWPX | DOCX | PPTX | PDF readable | PDF scanned |
| --- | --- | --- | --- | --- | --- | --- |
| `replace_cell` | 셀 값 변경 | 해당 없음 | 해당 없음 | 표 셀 확장 가능 | 해당 없음 | 해당 없음 |
| `replace_text` | 제한적 | 텍스트 치환 | 문단/run 치환 | shape 텍스트 치환 | 짧은 overlay 치환 | OCR anchor 필요 |
| `annotate` | 메모 가능 | notice/주석 후보 | comment 후보 | comment 후보 | highlight/comment | OCR bbox 필요 |
| `redact_overlay` | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 영역 가림 + 대체 텍스트 | 이미지 위 가림 |
| `regenerate` | 새 통합 문서 생성 | 새 HWP/HWPX 생성 후보 | 새 DOCX/PDF 생성 | 새 PPTX/PDF 생성 | HTML/PDF 재작성 | OCR 기반 재작성 |
| `set_cell_style` | range 단위 서식 변경(폰트 굵게, 배경색, 정렬, 테두리) | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |
| `set_number_format` | range 단위 표시 형식 변경(날짜, 천단위, 퍼센트 등) | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |
| `set_formula` | 단일 셀 수식 설정(SUM/AVERAGE/COUNT/COUNTA/MIN/MAX/IF) | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |

주의:

- 같은 `replace_text`라도 포맷별 구현은 다르다.
- PDF의 `replace_text`는 원본 텍스트 재흐름이 아니라 redaction/overlay 계열로 취급한다.
- 큰 PDF 수정은 `replace_text`가 아니라 `regenerate`로 분류한다.

## 7. Anchor 스키마

### 7.1 cell anchor

XLSX/CSV 우선.

```json
{
  "type": "cell",
  "sheet": "Sheet1",
  "cell": "D12",
  "row_index": 11,
  "col_index": 3
}
```

### 7.2 text_match anchor

HWP/HWPX/DOCX/PDF 공통 fallback.

대상 텍스트 키는 `target_text`가 기준이다. DOCX/PPTX patcher는 과거에 읽던
legacy 키 `text_match`도 기존 저장된 `DocumentChange` 하위호환을 위해
fallback으로 받아들이지만, 새로 생성되는 plan은 `target_text`만 사용한다.

`occurrence`는 대상 텍스트가 문서에 유일하게 출현할 때만 지정한다. 다중 출현
문서에 occurrence를 지정하면 resolver의 모호성 판정(AMBIGUOUS →
NEEDS_CONFIRMATION)을 우회해 침묵 오수정으로 이어지므로, 확신 없는 생성기는
occurrence를 생략해야 한다.

```json
{
  "type": "text_match",
  "target_text": "2025년 08월 11일",
  "context_before": "신청일시",
  "context_after": "무주택기간",
  "occurrence": 1,
  "page": 1
}
```

### 7.3 hwp_text anchor

`@rhwp/core` 기반 patcher가 사용할 수 있는 정밀 anchor.

```json
{
  "type": "hwp_text",
  "sec": 0,
  "para": 0,
  "char_offset": 12,
  "length": 3,
  "cell_context": {
    "parent_para": 0,
    "ctrl_idx": 3,
    "cell_idx": 2,
    "cell_para": 0
  },
  "fallback_text": "11월"
}
```

v0에서는 LLM이 이 anchor를 직접 만들지 않는다.

생성 주체:

```text
LLM text_match
  -> HWP patch worker searchAllText()
  -> hwp_text anchor 확정
```

### 7.4 pdf_bbox anchor

PyMuPDF 기반 PDF viewer/patcher용.

```json
{
  "type": "pdf_bbox",
  "page": 1,
  "rect": {
    "x0": 159.31,
    "y0": 679.18,
    "x1": 237.83,
    "y1": 692.18
  },
  "target_text": "성남여수(06)(A-2)"
}
```

v0에서는 readable PDF에서 `search_for()` 또는 텍스트 조각 병합으로 생성한다.

### 7.5 slide_shape anchor

PPTX용.

```json
{
  "type": "slide_shape",
  "slide_index": 0,
  "shape_index": 4,
  "row_index": null,
  "col_index": null
}
```

### 7.6 cell_range anchor (XLSX 전용, v1)

`set_cell_style` operation에서 사용한다. 자세한 검증 규칙은
`../feature-specs/document-format-editing-ax-v1-ko.md` 7.3-7.4절을 참조한다.

```json
{
  "type": "cell_range",
  "sheet": "Sheet1",
  "range": "A1:D1"
}
```

규칙:

- `type`은 `cell_range`
- `sheet`는 필수
- `range`는 A1 notation. 단일 셀 `"A1"`과 `"A1:A1"`을 모두 허용한다.
- 최대 200셀까지만 허용한다.

## 8. Patch payload 예시

### 8.1 XLSX 셀 변경

```json
{
  "operation_id": "op_xlsx_001",
  "format": "xlsx",
  "operation": "replace_cell",
  "title": "금액 오류 수정",
  "original": "1500",
  "replacement": "15000",
  "anchor": {
    "type": "cell",
    "sheet": "Sheet1",
    "cell": "D12"
  },
  "patch": {
    "method": "openpyxl_set_value",
    "value": "15000"
  }
}
```

### 8.1b XLSX 셀 서식 변경 (v1, `set_cell_style`)

```json
{
  "operation_id": "op_xlsx_style_001",
  "format": "xlsx",
  "operation": "set_cell_style",
  "title": "표 헤더 서식 정리",
  "reason": "헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.",
  "confidence": 0.86,
  "anchor": {
    "type": "cell_range",
    "sheet": "Sheet1",
    "range": "A1:D1"
  },
  "expected_context": {
    "sample_values": {
      "A1": "항목",
      "D1": "금액"
    },
    "non_empty_cells": ["A1", "B1", "C1", "D1"]
  },
  "patch": {
    "font_bold": true,
    "fill_color": "D9EAF7",
    "horizontal_alignment": "center",
    "vertical_alignment": "center",
    "border": "thin"
  }
}
```

patch whitelist (그 외 필드는 거부):

| 필드 | 타입 | 허용값 |
| --- | --- | --- |
| `font_bold` | boolean | `true` / `false` |
| `fill_color` | string | 6자리 `RRGGBB` (적용 시 `FF` ARGB prefix로 변환) |
| `horizontal_alignment` | string | `left` \| `center` \| `right` |
| `vertical_alignment` | string | `top` \| `center` \| `bottom` |
| `border` | string | `thin` \| `medium` \| `none` |

`expected_context`는 DB에는 별도 필드가 없으므로 저장 시 `patch.expected_context`로 병합한다.
검증 실패 조건과 backend 구현은 `../feature-specs/document-format-editing-ax-v1-ko.md` 7.4, 8.3절을 참조한다.

### 8.1c XLSX 표시 형식 변경 (다음 로드맵, `set_number_format`)

```json
{
  "operation_id": "op_xlsx_format_001",
  "format": "xlsx",
  "operation": "set_number_format",
  "title": "금액 열 표시 형식 정리",
  "reason": "금액이 콤마 없이 표시되어 자릿수를 읽기 어렵습니다.",
  "confidence": 0.88,
  "anchor": {
    "type": "cell_range",
    "sheet": "Sheet1",
    "range": "D2:D10"
  },
  "expected_context": {
    "sample_values": {
      "D2": "10000"
    },
    "non_empty_cells": ["D2"]
  },
  "patch": {
    "number_format": "#,##0원"
  }
}
```

patch whitelist (그 외 필드는 거부):

| 필드 | 타입 | 허용값 |
| --- | --- | --- |
| `number_format` | string | `yyyy-mm-dd` \| `yyyy. mm. dd` \| `#,##0` \| `#,##0원` \| `#,##0.00` \| `0.0%` \| `0.00%` |

anchor/range/expected_context 규칙은 `set_cell_style`(7.6절)과 동일하다(최대 200셀,
`sample_values`/`non_empty_cells` 필수, anchor.range 내부 셀만 허용).

### 8.1d XLSX 수식 설정 (다음 로드맵, `set_formula`)

```json
{
  "operation_id": "op_xlsx_formula_001",
  "format": "xlsx",
  "operation": "set_formula",
  "title": "금액 합계 셀 계산",
  "reason": "합계 행이 비어 있어 표 하단에 합계를 채워달라는 요청입니다.",
  "confidence": 0.82,
  "anchor": {
    "type": "cell",
    "sheet": "Sheet1",
    "cell": "D11"
  },
  "expected_context": {
    "sample_values": {
      "D2": "10000"
    },
    "non_empty_cells": ["D2"]
  },
  "patch": {
    "formula": "=SUM(D2:D10)"
  }
}
```

규칙:

- `anchor.type`은 `cell`만 허용한다(range 대상은 거부). 1차 범위는 단일 셀 수식 설정만 지원한다.
- `patch`는 `formula`만 허용하며 `SUM`/`AVERAGE`/`COUNT`/`COUNTA`/`MIN`/`MAX`/`IF` whitelist
  함수만 사용할 수 있다(중첩 호출 허용, 예: `IF(COUNT(...)>0,SUM(...),0)`).
- 외부 시트/통합문서 참조(`!`, `[...]`), URL, 문자열 연결(`&`), whitelist 밖 함수
  (`INDIRECT`, `HYPERLINK`, `WEBSERVICE` 등)는 모두 거부된다.
- `expected_context`는 대상 셀이 아니라 수식이 참조하는 데이터의 현재 값을 확인하는
  용도다(대상 셀은 수식을 넣기 전이라 보통 비어 있다).

검증 실패 조건과 backend 구현은 `../roadmap/document-editing-ax-next-roadmap-v1-ko.md`
6.Phase2-3절을 참조한다.

### 8.2 HWP 텍스트 변경

```json
{
  "operation_id": "op_hwp_001",
  "format": "hwp",
  "operation": "replace_text",
  "title": "월 표기 수정",
  "original": "11월",
  "replacement": "12월",
  "anchor": {
    "type": "text_match",
    "target_text": "11월",
    "occurrence": 1
  },
  "patch": {
    "method": "rhwp_replace_text",
    "fallback_method": "rhwp_replace_all"
  }
}
```

### 8.3 PDF 검토 주석

```json
{
  "operation_id": "op_pdf_001",
  "format": "pdf",
  "operation": "annotate",
  "title": "누락 항목 표시",
  "original": "",
  "replacement": "유선 전화번호 확인 필요",
  "anchor": {
    "type": "text_match",
    "target_text": "전화번호가 없습니다.",
    "page": 1
  },
  "patch": {
    "method": "pymupdf_highlight_comment",
    "comment": "신청자 인적사항에 유선 전화번호가 누락되었습니다."
  }
}
```

### 8.4 PDF 짧은 텍스트 overlay 수정

```json
{
  "operation_id": "op_pdf_002",
  "format": "pdf",
  "operation": "redact_overlay",
  "title": "날짜 형식 통일",
  "original": "2025년 08월 11일",
  "replacement": "2025-08-11",
  "anchor": {
    "type": "pdf_bbox",
    "page": 1,
    "rect": {
      "x0": 414.43,
      "y0": 735.87,
      "x1": 484.44,
      "y1": 748.87
    },
    "target_text": "2025년 08월 11일"
  },
  "patch": {
    "method": "pymupdf_redact_overlay",
    "font": "auto",
    "font_size": "fit",
    "fill": "white"
  },
  "risk": {
    "level": "medium",
    "requires_user_confirmation": true,
    "notes": ["PDF는 원본 레이아웃 재흐름을 지원하지 않습니다."]
  }
}
```

### 8.5 PDF 재생성

```json
{
  "operation_id": "op_pdf_003",
  "format": "pdf",
  "operation": "regenerate",
  "title": "검토 의견서 재작성본 생성",
  "original": null,
  "replacement": null,
  "anchor": {
    "type": "document"
  },
  "patch": {
    "method": "html_to_pdf",
    "template": "review_report_v1",
    "structured_document": {
      "title": "계약서 검토 의견서",
      "sections": []
    }
  },
  "risk": {
    "level": "high",
    "requires_user_confirmation": true,
    "notes": ["원본 PDF를 직접 수정하지 않고 새 PDF를 생성합니다."]
  }
}
```

## 9. strategy.kind

`PatchPlan.strategy.kind`는 결과물 생성 방식을 요약한다.

```text
patch
review_copy
regenerate
mixed
```

### patch

원본 파일 구조를 유지하고 직접 수정한다.

예:

- XLSX 셀 변경
- HWP 텍스트 치환
- PPTX shape 텍스트 치환

### review_copy

원본 위에 하이라이트/주석/마스킹을 얹은 검토본을 만든다.

예:

- PDF highlight annotation
- PDF comment
- PDF redaction preview

### regenerate

원본 내용을 바탕으로 새 문서를 생성한다.

예:

- PDF 내용을 보고 보고서형 PDF 재작성
- 스캔 PDF OCR 결과를 구조화 문서로 재생성

### mixed

일부는 직접 patch, 일부는 검토 주석 또는 재생성을 함께 수행한다.

## 10. DocumentChange 매핑

권장 필드:

```text
DocumentChange
  id
  owner
  upload_log
  source_message
  plan_id
  operation_id
  format
  operation
  title
  original
  replacement
  reason
  confidence
  anchor JSON
  patch JSON
  status: pending | applied | rejected
  risk_level
  created_at
  updated_at
```

초기에는 `DocumentChange.status`를 프론트의 적용/거절 상태 원천으로 삼는다.

## 11. DocumentVersion 매핑

권장 필드:

```text
DocumentVersion
  id
  owner
  upload_log
  parent_version
  version_number
  label
  summary
  artifact_file
  artifact_format
  status: original | draft | generating | ready | failed
  applied_change_ids JSON
  created_at
  updated_at
```

뷰어 상단의 수정 내역/버전 탭은 `DocumentVersion` 목록을 사용한다.

## 12. Patcher 책임

patcher는 다음을 보장해야 한다.

- 지원하지 않는 operation은 실패로 반환한다.
- anchor를 다시 검증한다.
- original 값이 실제 문서 내용과 다르면 충돌로 처리한다.
- patch 결과를 새 파일로 저장한다.
- 원본 파일은 덮어쓰지 않는다.
- 결과 파일을 다시 열어 최소 검증한다.

## 13. 초기 구현 우선순위

1. XLSX `replace_cell`
2. HWP `replace_text` using `@rhwp/core` Node worker
3. PDF `annotate` using PyMuPDF
4. PDF `redact_overlay` using PyMuPDF
5. PDF `regenerate` using HTML to PDF
6. DOCX/PPTX patch

## 14. 미해결 질문

- `apply` 버튼 클릭 시 즉시 `DocumentChange.status`를 저장할지, 로컬 draft 후 “수정본 생성”에서 저장할지
- `PatchPlan`을 DB에 원본 JSON으로 보존할지
- LLM 응답 실패/부분 성공 시 사용자에게 어떤 상태로 보여줄지
- PDF overlay 결과를 제품에서 “수정본”이라 부를지 “검토본”이라 부를지
- HWP patch worker를 `ax-engine`에 둘지 `backend`에 둘지
- `@rhwp/core` 서버 사용 시 Node 프로세스 타임아웃/메모리 제한 기준
