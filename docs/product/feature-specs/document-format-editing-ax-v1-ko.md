# Office-AX 문서 양식 수정 AX v1

문서 상태: v1 POC 배경 문서. XLSX `set_cell_style`과 양식 수정의 제품/기술 가설을 설명하며, 현재 MVP 전체 범위는 `../strategy/mvp-scope-and-gap-v1-ko.md`를 우선한다.

## 1. 문서의 위치

이 문서는 기존 v0 기획 위에 이어지는 v1 제품 기획이다.

v0 문서:

- `../strategy/viewer-first-workflow-automation-v0-ko.md`
- `../architecture/document-workflow-implementation-design-v0-ko.md`
- `../contracts/patch-plan-schema-v0-ko.md`

v0의 핵심은 다음이었다.

- 사용자는 문서를 업로드한다.
- AI에게 검토나 수정을 요청한다.
- AI는 일반 답변이 아니라 구조화된 `PatchPlan`을 만든다.
- 서버는 `DocumentChange`로 변경 제안을 저장한다.
- 사용자는 뷰어에서 제안을 적용하거나 거절한다.
- patcher는 승인된 변경만 실제 파일에 반영한다.
- 결과물은 `DocumentVersion`과 artifact로 보존된다.

즉 v0는 "문서 옆에서 말하는 AI"가 아니라 "문서 위에서 수정 제안을 만들고 실제 파일을 생성하는 AI"를 만드는 단계였다.

v1은 그 다음 단계다.

v1의 목표는 Office-AX가 단순 텍스트 치환기를 넘어, 업무 문서의 표, 양식, 서식을 안전하게 수정할 수 있음을 증명하는 것이다.

## 2. 문제 정의

현재 문서 수정 기능은 대부분 다음 범위에 머문다.

- XLSX 셀 값 변경
- DOCX/PPTX/HWP 텍스트 치환
- PDF annotate 또는 redact overlay

이것만으로도 "AI가 문서를 실제로 수정한다"는 기본 경험은 만들 수 있다.

하지만 사용자가 기대하는 문서 수정은 값과 문장만 바꾸는 것이 아니다.

실제 업무 문서에서는 다음 요청이 자주 나온다.

- 표 헤더를 보기 좋게 정리해줘.
- 합계 행을 추가해줘.
- 금액 열은 오른쪽 정렬해줘.
- 날짜/금액 표시 형식을 통일해줘.
- 보고서 표를 회사 양식처럼 만들어줘.
- 누락된 항목 행을 넣어줘.
- 문서 제목과 소제목 체계를 정리해줘.
- 표 안의 특정 열을 강조해줘.

이런 요청을 처리하지 못하면 Office-AX는 "문서 수정 AX"라기보다 "문서 텍스트 치환 도구"에 머문다.

따라서 v1은 문서의 내용뿐 아니라 문서의 양식까지 수정하는 방향을 열어야 한다.

## 3. 제품 원칙

### 3.1 자유 편집기가 아니라 안전한 patcher다

Office-AX는 브라우저 안에서 사용자가 직접 문서를 편집하는 편집기가 아니다.

사용자는 프롬프트로 요청한다.

LLM은 수정 계획을 만든다.

서버 patcher는 검증 가능한 operation만 적용한다.

따라서 v1의 핵심은 "무엇이든 고치는 AI"가 아니라 "정의된 operation을 안전하게 늘려가는 문서 패처"다.

### 3.2 LLM은 계획하고, patcher가 수정한다

LLM이 파일을 직접 수정하게 하지 않는다.

LLM의 책임:

- 문서에서 수정이 필요한 위치를 찾는다.
- 어떤 operation이 필요한지 결정한다.
- `PatchPlan` JSON을 생성한다.
- 사용자에게 설명 가능한 reason/title을 만든다.

서버의 책임:

- operation 스키마를 검증한다.
- 문서 상태와 `expected_context`를 대조한다.
- 포맷별 patcher로 실제 파일을 수정한다.
- 결과 artifact를 저장한다.

### 3.3 잘못된 위치에 적용하지 않는 것이 가장 중요하다

서식 수정은 값 변경보다 위험하다.

값 변경은 `original`과 현재 셀 값을 비교할 수 있다.

하지만 서식 변경은 "현재 스타일"을 비교하기 어렵다.

따라서 v1 operation에는 `expected_context`가 필요하다.

예:

- 이 range가 실제로 헤더인지 확인한다.
- 특정 셀의 값이 기대값과 맞는지 확인한다.
- 핵심 셀이 비어 있지 않은지 확인한다.
- range 크기가 과도하게 크지 않은지 확인한다.

검증이 실패하면 해당 change는 적용하지 않는다.

### 3.4 patch와 regenerate는 분리한다

부분 수정 patch와 전체 재생성 regenerate는 다른 제품이다.

patch:

- 원본 파일 bytes가 있다.
- 승인된 변경 목록이 있다.
- patcher가 원본에 변경을 적용한다.
- 결과 artifact가 생성된다.

regenerate:

- 원본을 참고하지만 새 문서를 생성한다.
- 템플릿, 문서 생성 모델, 레이아웃 엔진이 필요하다.
- 원본 위치 anchor와 1:1로 대응되지 않을 수 있다.

v1은 patch를 확장한다.

regenerate는 별도 트랙으로 남긴다.

## 4. 문서 수정 레벨

v1에서는 문서 수정을 세 단계로 본다.

### 4.1 내용 수정

문서의 값이나 문장을 바꾼다.

예:

- 셀 값 변경
- 텍스트 치환
- 날짜 형식 통일
- 금액 표기 수정
- 누락된 전화번호 표시

현재 v0의 주력 범위다.

### 4.2 서식 수정

문서의 의미는 유지하면서 표시 방식을 바꾼다.

예:

- 글꼴 굵게
- 배경색
- 글자색
- 셀 테두리
- 가로/세로 정렬
- 숫자 표시 형식
- 표 헤더 강조

v1의 첫 목표다.

### 4.3 구조 수정

문서 안에 새 블록을 넣거나 기존 구조를 바꾼다.

예:

- 표 행 추가
- 표 열 추가
- 합계 행 삽입
- 섹션 추가
- 슬라이드 블록 추가

구조 수정은 anchor 이동 문제가 있으므로 v1 초반에는 제한적으로 다룬다.

특히 XLSX 행 삽입은 여러 change를 동시에 적용할 때 행 번호가 밀리는 문제가 있다.

따라서 첫 POC에서는 제외한다.

## 5. 포맷별 전략

### 5.1 XLSX

우선순위 1번이다.

이유:

- `openpyxl`이 셀 값, 스타일, 테두리, 정렬, 수식, 병합, 행/열 삽입을 API로 제공한다.
- 중소기업 업무에서 정산서, 견적서, 발주서, 매출표, 청구서 등 XLSX 체감 가치가 크다.
- 뷰어에서 셀/range anchor를 비교적 명확하게 표현할 수 있다.
- POC 성공 가능성이 높다.

v1 초기 지원 후보:

- `set_cell_style`
- `set_formula`

후속 후보:

- `insert_table_row`
- `insert_table_column`
- `merge_cells`
- `set_number_format`
- `copy_row_style`

### 5.2 DOCX

우선순위 2번이다.

초기 범위는 표 셀 텍스트 수정과 제한적 문단 스타일 수정이다.

가능한 작업:

- 표 셀 텍스트 변경
- 행 추가
- 문단 굵게/정렬
- 일부 run 스타일 조정

주의:

- `python-docx`는 레이아웃 엔진이 아니다.
- 머리말, 꼬리말, 섹션, 복잡한 표 스타일은 제한이 있다.
- "문서 전체를 회사 양식으로 재작성"은 patch가 아니라 regenerate에 가깝다.

### 5.3 HWP

한국 시장에서 중요하지만 기술 리스크가 크다.

현재는 텍스트 치환이 먼저 안정화되어야 한다.

표/양식 수정은 별도 POC가 필요하다.

확인해야 할 것:

- `@rhwp/core`가 표 셀 구조를 안정적으로 읽을 수 있는가
- 표 셀 텍스트 변경이 가능한가
- 행 추가/삭제 API가 있는가
- 저장 후 한글에서 정상 열리는가
- 스타일 변경이 보존되는가

v1에서는 HWP 표 구조 변경을 본 구현 범위에 넣지 않는다.

### 5.4 PPTX

시각적 임팩트는 있지만 초기 업무 가치와 구현 표면을 고려하면 뒤로 둔다.

가능한 작업:

- 텍스트 박스 내용 변경
- 도형 색상 변경
- 표 셀 텍스트 변경
- 일부 스타일 변경

주의:

- PPTX는 셀보다 셰이프 중심 모델이다.
- 같은 "표"라도 실제로는 shape/tree 구조를 다뤄야 한다.
- 디자인 자동화는 patch보다 별도 디자인 엔진에 가깝다.

### 5.5 PDF

PDF는 구조 수정 대상이 아니다.

현재 전략을 유지한다.

- annotate
- redact overlay
- 필요 시 regenerate

표/양식 수정은 PDF 내부를 직접 수정하기보다 원본 포맷이나 HTML/PDF 재생성으로 다루는 것이 맞다.

## 6. v1 첫 POC: XLSX set_cell_style

### 6.1 목표

`set_cell_style` operation 하나로 "문서 양식 수정" 감성을 검증한다.

예상 사용자 요청:

```text
표 헤더를 보기 좋게 정리해줘.
```

AI 제안:

```text
Sheet1 A1:D1 헤더 영역을 굵게, 가운데 정렬, 연한 파란 배경, 얇은 테두리로 변경합니다.
```

결과:

- 사용자는 ChangeSuggestionCard에서 range 위치를 확인한다.
- ChangeSuggestionCard에서 서식 변경 내용을 확인한다.
- 적용 후 artifact를 다운로드한다.
- XLSX 파일에서 헤더 서식이 실제로 변경되어 있다.

### 6.2 제외 범위

1차 POC에서 제외한다.

- 행 삽입
- 열 삽입
- 셀 병합
- 수식 삽입
- 숫자 형식 변경
- DOCX/HWP/PPTX 서식 변경
- PDF 구조 수정
- 전체 문서 재생성

### 6.3 operation 예시

```json
{
  "operation_id": "op_001",
  "format": "xlsx",
  "operation": "set_cell_style",
  "title": "표 헤더 서식 정리",
  "reason": "헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.",
  "confidence": 0.86,
  "risk": {
    "level": "low"
  },
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

## 7. PatchPlan 스키마 확장

### 7.1 원칙

포맷별 operation으로 정의한다.

공통 operation으로 무리하게 추상화하지 않는다.

이유:

- XLSX의 셀 스타일과 DOCX의 문단 스타일은 표현 방식이 다르다.
- PPTX는 shape 중심이다.
- HWP는 라이브러리 API 확인이 필요하다.
- 공통 스키마를 만들면 가장 약한 기능만 남는다.

따라서 `set_cell_style`은 XLSX 전용으로 정의한다.

### 7.2 필수 필드

`set_cell_style` operation 필수 필드:

- `operation_id`
- `format = "xlsx"`
- `operation = "set_cell_style"`
- `title`
- `reason`
- `confidence`
- `anchor`
- `expected_context`
- `patch`

### 7.3 anchor

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
- `range`는 A1 notation
- 단일 셀은 `"A1"`과 `"A1:A1"`을 모두 허용한다. `openpyxl.utils.cell.range_boundaries`가 두 표현을 동일하게 처리하므로 별도 분기 없이 검증한다.
- 1차 구현은 최대 200셀까지만 허용한다.

### 7.4 expected_context

```json
{
  "sample_values": {
    "A1": "항목",
    "D1": "금액"
  },
  "non_empty_cells": ["A1", "B1", "C1", "D1"]
}
```

검증 목적:

- LLM이 잘못된 range를 찍었는지 확인한다.
- 사용자가 보는 문서 상태와 patcher가 적용할 문서 상태가 같은지 확인한다.
- 서식 변경이 엉뚱한 영역에 적용되는 것을 막는다.

검증 실패 조건:

- sheet가 없다.
- range 문법이 잘못됐다.
- range가 너무 크다.
- `sample_values`가 현재 값과 다르다.
- `non_empty_cells` 중 빈 셀이 있다.

### 7.5 patch whitelist

1차 허용:

```json
{
  "font_bold": true,
  "fill_color": "D9EAF7",
  "horizontal_alignment": "center",
  "vertical_alignment": "center",
  "border": "thin"
}
```

허용값:

- `font_bold`: boolean
- `fill_color`: `RRGGBB`
- `horizontal_alignment`: `left | center | right`
- `vertical_alignment`: `top | center | bottom`
- `border`: `thin | medium | none`

금지:

- 임의 객체
- 임의 CSS
- 임의 Python/openpyxl 속성명
- 외부 폰트 파일 경로
- 수식 실행

색상 처리 규칙:

- PatchPlan에는 6자리 `RRGGBB`만 허용한다.
- openpyxl `PatternFill` 적용 시에는 반드시 `"FF" + fill_color` 형태의 8자리 ARGB로 변환한다.
- `PatternFill(fgColor="D9EAF7", fill_type="solid")`처럼 6자리 값을 그대로 넘기면 openpyxl이 `00D9EAF7`로 저장할 수 있다. 이 경우 alpha가 `00`이 되어 배경색이 보이지 않는 파일이 생성될 수 있다.
- 따라서 `fill_color = "D9EAF7"`은 실제 적용 시 `fgColor = "FFD9EAF7"`로 변환한다.

후속 후보:

- `font_color`
- `font_size`
- `number_format`
- `wrap_text`

## 8. Backend 구현 설계

### 8.1 모델 변경

모델 변경은 필요 없다.

이미 `DocumentChange`에 다음 필드가 있다.

- `operation`
- `anchor`
- `patch`
- `reason`
- `risk_level`
- `status`

`expected_context`는 두 가지 선택지가 있다.

1. `anchor.expected_context`로 넣는다.
2. `patch.expected_context`로 넣는다.
3. `DocumentChange`에 별도 JSONField를 추가한다.

v1 POC에서는 모델 변경을 피하기 위해 `patch.expected_context` 또는 top-level operation의 `expected_context`를 `patch`에 보존하는 방식이 현실적이다.

다만 장기적으로는 `DocumentChange.expected_context` 필드를 분리하는 것이 더 명확하다.

POC 추천:

```json
{
  "patch": {
    "expected_context": {
      "sample_values": {
        "A1": "항목"
      }
    },
    "style": {
      "font_bold": true,
      "fill_color": "D9EAF7"
    }
  }
}
```

하지만 프론트 표시와 patcher 단순성을 위해, 백엔드 저장 시 다음처럼 정규화하는 것도 가능하다.

```json
{
  "patch": {
    "font_bold": true,
    "fill_color": "D9EAF7",
    "horizontal_alignment": "center",
    "expected_context": {
      "sample_values": {
        "A1": "항목"
      }
    }
  }
}
```

### 8.2 LLM PatchPlan 생성

현재 LLM 프롬프트의 allowed operation에 `set_cell_style`을 추가한다.

단, 바로 모든 문서에 허용하지 않는다.

조건:

- `source_type == "excel"` 또는 `format == "xlsx"`일 때만 허용
- 프롬프트에 명확히 "style operation은 xlsx에서만 가능"을 넣는다.
- expected_context 생성 규칙을 명시한다.

LLM에게 요구할 내용:

- range를 너무 크게 잡지 말 것
- 헤더 추정 시 sample_values를 반드시 넣을 것
- 사용자가 서식 변경을 요청하지 않았다면 임의로 과도한 스타일을 적용하지 말 것
- 불확실하면 operation을 생성하지 말 것

### 8.3 patcher 구조

현재 patcher는 다음 3단계 구조를 지향한다.

```text
collect_applied_changes
render_*
persist_patch_result
```

`set_cell_style`은 `render_xlsx` 안에서 처리한다.

권장 흐름:

```text
render_xlsx(original_bytes, changes)
  -> workbook load
  -> replace_cell changes 처리
  -> set_cell_style changes 처리
  -> PatchResult 반환
```

세부 함수:

```text
validate_xlsx_style_change(workbook, change) -> ValidationResult
apply_xlsx_cell_style(workbook, change) -> None
```

검증 실패:

- `PatchResult.failed_items`에 `operation_id`, `reason` 추가
- DB 저장은 `persist_patch_result`가 담당

### 8.4 openpyxl 적용 방식

사용 API:

- `openpyxl.styles.Font`
- `openpyxl.styles.PatternFill`
- `openpyxl.styles.Border`
- `openpyxl.styles.Side`
- `openpyxl.styles.Alignment`
- `openpyxl.utils.cell.range_boundaries`

적용 예:

```python
for row in ws[range_ref]:
    for cell in row:
        if font_bold is not None:
            cell.font = copy(cell.font)
            cell.font = Font(
                name=cell.font.name,
                size=cell.font.sz,
                bold=font_bold,
                italic=cell.font.italic,
                color=cell.font.color,
            )
```

주의:

- openpyxl 스타일 객체는 immutable에 가깝게 다뤄야 하므로 기존 스타일을 보존하며 새 객체를 만든다.
- 1차 구현에서는 모든 기존 스타일 완전 보존보다 허용 필드만 안전하게 덮어쓰는 것을 우선한다.
- 색상은 PatchPlan의 6자리 `RRGGBB`를 그대로 넘기지 않고, `PatternFill` 적용 직전에 `FF` alpha prefix를 붙여 8자리 ARGB로 변환한다. 예: `D9EAF7` -> `FFD9EAF7`.

## 9. Frontend 구현 설계

### 9.1 suggestion 정규화

`patch_changes`에서 `operation = "set_cell_style"`이 들어온다.

정규화 결과에는 다음 필드가 있어야 한다.

- `operation`
- `format`
- `anchor`
- `patch`
- `title`
- `reason`
- `changeDbId`

기존 `replace_*` UI는 원문/수정안 diff에 적합하다.

`set_cell_style`은 diff가 아니라 operation summary로 보여야 한다.

### 9.2 ChangeSuggestionCard 표시

표시 예:

```text
표 헤더 서식 정리
Sheet1 A1:D1
굵게 · 배경색 D9EAF7 · 가운데 정렬 · 얇은 테두리

이유:
헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.
```

UI 원칙:

- `original`이 비어 있다고 빈 diff를 보여주지 않는다.
- `replacement`가 비어 있어도 정상 제안으로 표시한다.
- operation별로 다른 설명 문장을 만든다.
- apply/reject 흐름은 기존과 동일하게 둔다.

### 9.3 하이라이트

1차는 패널 설명 중심으로 충분하다.

가능하면 XLSX viewer에서 range 하이라이트를 지원한다.

우선순위:

1. ChangeSuggestionCard에서 range 표시
2. Excel viewer에서 range outline
3. 스타일 적용 전/후 미리보기

1차 POC에서는 1번만으로도 충분하다.

## 10. 충돌 처리

현재 accept-all 충돌 해소는 anchor 기반이다.

`set_cell_style`은 range anchor를 사용하므로 충돌 판정이 복잡해질 수 있다.

1차 POC 정책:

- 같은 sheet + 같은 range + 같은 operation이면 충돌
- 기존 exact anchor 기준을 유지한다.
- range overlap은 후속 과제로 둔다.

후속 과제:

- `A1:D1`과 `B1:C1`이 겹치는지 판단
- `set_cell_style`과 `replace_cell`이 충돌하는지 판단
- style patch끼리 병합 가능한지 판단

초기에는 병합하지 않는다.

동일 위치에 여러 style operation이 있으면 confidence 기준으로 하나만 적용한다.

## 11. 테스트 전략

### 11.1 Backend

필수 테스트:

- `set_cell_style` 성공 시 artifact가 저장된다.
- 결과 XLSX의 대상 range가 bold 처리된다.
- 결과 XLSX의 fill color가 적용된다.
- alignment가 적용된다.
- border가 적용된다.
- sheet가 없으면 해당 change가 failed 된다.
- range 문법이 잘못되면 failed 된다.
- range가 너무 크면 failed 된다.
- sample value가 불일치하면 failed 된다.
- non_empty_cells가 비어 있으면 failed 된다.
- invalid fill_color는 failed 된다.
- invalid alignment는 failed 된다.
- invalid border는 failed 된다.
- `replace_cell`과 `set_cell_style`이 같은 파일에서 함께 적용된다.
- 모든 change가 실패하면 version이 failed 된다.
- 일부 성공/일부 실패면 version은 ready, 실패 change는 failed가 된다.

### 11.2 Frontend

필수 테스트:

- `set_cell_style` suggestion이 diff UI가 아니라 style summary로 표시된다.
- patch 내용이 사람이 읽을 수 있는 label로 표시된다.
- `changeDbId`가 유지된다.
- apply/reject 버튼은 기존과 동일하게 동작한다.
- `patch_changes` 우선순위가 유지된다.
- 기존 replace suggestion UI가 깨지지 않는다.

### 11.3 수동 검증

샘플 XLSX:

- 1행에 헤더가 있는 간단한 표
- 헤더에 스타일이 없는 상태
- 사용자가 "표 헤더 보기 좋게 정리해줘" 요청
- 제안 생성
- 적용
- 수정본 생성
- 다운로드 후 Excel/Numbers/LibreOffice에서 열기

확인:

- 파일이 정상 열리는가
- 헤더 서식이 적용되었는가
- 기존 셀 값이 유지되는가
- 다른 시트가 훼손되지 않았는가

## 12. 단계별 구현 계획

### Phase 1: 문서 및 스키마

작업:

- `../contracts/patch-plan-schema-v0-ko.md`에 `xlsx.set_cell_style` 섹션 추가
- allowed operation 표 업데이트
- expected_context 규칙 추가
- regenerate는 별도 트랙임을 명시

산출물:

- 스키마 문서 업데이트
- 구현자용 프롬프트

### Phase 2: Backend patcher

작업:

- `render_xlsx`에서 `set_cell_style` change 수집/처리
- `validate_xlsx_style_change`
- `apply_xlsx_cell_style`
- 실패 reason 표준화
- 테스트 추가

산출물:

- XLSX style patcher
- artifact 저장 흐름 유지

### Phase 3: LLM PatchPlan 생성

작업:

- `_PATCH_PLAN_SYSTEM_PROMPT`에 `set_cell_style` 추가
- XLSX 문맥에서만 허용
- expected_context 생성 규칙 추가
- 불확실하면 생성하지 말라는 지침 추가

산출물:

- LLM이 style operation을 생성할 수 있는 prompt

### Phase 4: Frontend suggestion UI

작업:

- `ChangeSuggestionCard` operation 분기
- style patch label formatter
- `set_cell_style` 테스트 추가

산출물:

- 서식 변경 제안 카드

### Phase 5: 통합 검증

작업:

- XLSX 샘플로 end-to-end 검증
- patch plan 생성부터 artifact 다운로드까지 확인
- 실패 케이스 확인

산출물:

- v1 POC 데모 가능 상태

## 13. 성공 기준

v1 POC 성공 기준:

- 사용자가 "표 헤더 정리" 같은 자연어 요청을 한다.
- Office-AX가 `set_cell_style` 제안을 만든다.
- 사용자는 제안을 적용/거절할 수 있다.
- 수정본 생성 후 artifact를 다운로드할 수 있다.
- 다운로드한 XLSX에서 실제 서식이 바뀌어 있다.
- 잘못된 range나 불일치 context는 적용되지 않는다.

실패 기준:

- LLM이 엉뚱한 range에 서식을 적용한다.
- 검증 없이 큰 영역을 꾸민다.
- artifact가 열리지 않는다.
- 기존 값이 훼손된다.
- UI가 빈 원문/수정안 diff를 보여준다.

## 14. 후속 로드맵

### 14.1 set_formula

`replace_cell`과 유사하므로 구현 난도가 낮다.

예:

```json
{
  "operation": "set_formula",
  "format": "xlsx",
  "anchor": {
    "type": "cell",
    "sheet": "Sheet1",
    "cell": "D13"
  },
  "expected_context": {
    "blank": true
  },
  "patch": {
    "formula": "=SUM(D2:D12)"
  }
}
```

### 14.2 insert_table_row

구조 수정의 첫 후보지만 anchor shift 문제가 있다.

설계 필요:

- 여러 row insertion의 적용 순서
- after_row 기준을 원본 기준으로 볼지, 변경 후 기준으로 볼지
- insertion 이후 후속 change anchor 재계산
- 스타일 복사 방식

### 14.3 DOCX table cell

후속 후보:

- `update_table_cell`
- `insert_table_row`

단, 스타일 변경보다 표 셀 텍스트 수정부터 시작한다.

### 14.4 HWP table POC

별도 POC로 진행한다.

질문:

- 표 셀 위치를 안정적으로 식별할 수 있는가
- 셀 텍스트 변경이 가능한가
- 행 추가가 가능한가
- 결과 파일이 한글에서 안정적으로 열리는가

### 14.5 regenerate

전체 재생성은 별도 제품 트랙이다.

필요한 것:

- 템플릿 모델
- 새 문서 생성 엔진
- 원본/참조 문서 기반 컨텍스트 구성
- 미리보기와 비교 UX
- provenance 기록

v1 patcher와 섞지 않는다.

## 15. 의사결정 요약

확정:

- 기존 v0는 viewer-first workflow, PatchPlan, DocumentVersion, artifact 기반으로 정의한다.
- v1은 문서 양식 수정 AX로 정의한다.
- 첫 POC는 XLSX `set_cell_style` 하나로 제한한다.
- `expected_context`를 안전장치로 도입한다.
- operation은 포맷별로 정의한다.
- regenerate는 별도 트랙이다.

보류:

- `expected_context`를 별도 모델 필드로 분리할지
- range overlap 충돌 판정
- XLSX 행 삽입
- DOCX/HWP/PPTX 양식 수정
- PDF regenerate

다음 작업:

1. `../contracts/patch-plan-schema-v0-ko.md`에 `xlsx.set_cell_style` 추가
2. backend `render_xlsx`에 style operation 구현
3. frontend `ChangeSuggestionCard`에 operation별 표시 추가
4. XLSX 샘플로 E2E 검증
