# Office-AX 문서 수정/생성 실행 레이어 설계 v1

문서 상태: 활성 설계 문서. 문서 수정/생성에서 LLM과 백엔드의 책임 분리, TargetResolver 일반화, Patch Contract 확장 방향, render validation, 베타 전 최소 범위를 고정한다.

관련 문서:

- `../contracts/patch-plan-schema-v0-ko.md`: 현재 PatchPlan operation/anchor/patch 계약. 이 문서의 6절이 확정되면 함께 갱신한다.
- `../roadmap/document-editing-ax-next-roadmap-v1-ko.md`: 구현 순서. 이 문서의 10절이 확정되면 함께 갱신한다.
- `../strategy/closed-beta-launch-plan-v1-ko.md`: 베타 공개 범위와 마스킹/민감정보 정책.
- `../architecture/stack-library-audit-v1-ko.md`: PDF/HWP 라이브러리 판단.

## 1. 문서의 목적

문서 수정/생성에서 반복되는 문제는 LLM 성능 부족이 아니라, LLM 결과를 실제 문서 artifact로 안전하게 실행하는 제품/백엔드 레이어가 약한 데 있다.

이 문서는 다음을 고정한다.

1. 작업 복잡도 계층(T0~T3)과 각 계층에서 LLM에 필요한 정보
2. LLM과 백엔드의 책임 재배치
3. AnchorResolver를 포맷 공통으로 일반화하는 방식 (클래스 계층이 아니라 wire contract)
4. T1/T2 Patch Contract 확장 방향
5. render/structural validation의 최소 invariant
6. 베타 전 최소 구현 범위와 베타 후 확장 범위

"완전한 파서 고도화"는 목표가 아니다. 목표는 문서 수정 도구로서의 기본기와 신뢰성이다.

## 2. 문제 정의

현재 흐름:

```text
파일 업로드
  → ax-engine parser 텍스트 추출
  → PII 마스킹 (analyze_document, text_chat 경로)
  → LLM에 추출 텍스트만 전달
  → LLM이 요약 / patch intent / PatchPlan 생성
  → 백엔드가 patcher로 실제 artifact 생성
```

이 구조는 단순 텍스트 수정에는 충분하지만, 다음 정보가 LLM에 전달되지 않는다.

- 좌표, 줄/문단 구조, 표 구조
- 라벨-값 관계 (어떤 텍스트가 정적 라벨이고 어떤 영역이 입력값인지)
- PDF 내부 그리기 순서와 실제 렌더링 결과

그래서 LLM은 "내용 이해"는 잘하지만 "어디를 어떻게 고쳐서 실제 파일로 만들 것인가"에 약하다.

핵심 진단: 지금까지 문제가 된 것은 LLM-heavy냐 BE-heavy냐가 아니라, LLM과 백엔드 사이의 계약이 약했다는 점이다. PR #31(PDF AnchorResolver)이 정확히 이 계약의 첫 번째 강화였다.

## 3. 작업 복잡도 계층 (T0~T3)

| Tier | 예시 | LLM에 필요한 정보 | 현재 상태 |
|---|---|---|---|
| **T0** 값 교체 | 날짜/이름/금액 치환 | 원문 텍스트 | 구현됨 (`replace_cell`, `replace_text`) |
| **T1** 위치 해석이 어려운 값 교체 | 빈칸 채움형 PDF, 동일 텍스트 다중 출현 | T0 + 읽기순서 token, occurrence | PDF 해결(PR #31 AnchorResolver), DOCX/HWP 부분적 |
| **T2** 구조화된 필드/표 수정 | 라벨-값 필드 채우기, 표 셀 수정, 행/열 삽입 | T1 + 표/영역의 구조 스키마 | 미구현 (구조 수정은 2026-07-01 보류 결정) |
| **T3** 신규 생성/자유 레이아웃 | RAG 양식 기반 문서 생성, 표/도표 신규 배치 | T2 + page render image 또는 crop, 문체/양식 예시 | 미구현 |

핵심 관찰 두 가지:

1. **T0/T1은 "어디를 찾을지"의 문제(resolver 문제)이고, T3부터 비로소 시각 정보 없이는 판단이 불가능한 문제다.** "이미지를 언제 LLM에 넘길지"는 사실 "T3을 언제 시작할지"와 같은 질문이다.
2. **T2가 항상 vision/image를 요구하지 않는다.** XLSX는 workbook/sheet/cell, DOCX는 paragraph/run/table/cell 구조가 파일 포맷 자체에 이미 있다. 표가 객체가 아니라 시각적 선 배치인 것은 PDF뿐이다. 따라서 T2의 기본 계약은 이미지 기반이 아니라 **structured candidate 기반**이어야 한다.

## 4. LLM과 백엔드의 책임 재배치

LLM이 담당한다:

- 사용자 자연어 요청을 patch intent로 구조화
- original/replacement 추출, value_type 판단 (date/name/money/text/table 등)
- 문체/어투 반영, 양식 구조 이해, 라벨-값 관계 추론
- 표/도표 내용 구성
- 모호할 때 사용자에게 물어볼 질문 생성
- PatchPlan 초안 생성

백엔드가 담당한다:

- 원본 파일 저장/권한/버전 관리
- parser/extractor 실행, token/bbox/page/line/block 구조 생성
- 포맷별 renderer/patcher, deterministic resolver
- PatchPlan schema 검증, 후보 점수화, 모호성 판정
- 실제 artifact 생성, render 후 검증
- 상태 관리 (`DRAFT`/`GENERATING`/`READY`/`FAILED`/`NEEDS_CONFIRMATION`)

원칙: "원본 파일 통째로 LLM에게 알아서 수정해줘"는 기본 경로가 아니다. 백엔드가 통제 가능한 구조로 정보를 추출해 LLM에 주고, 실제 파일 반영과 검증은 백엔드가 통제한다.

## 5. TargetResolver — 클래스 계층이 아니라 wire contract

### 5.1 왜 공통 클래스 상속이 아닌가

PDF `AnchorResolver`를 HWP/DOCX로 "코드 재사용"하는 것은 부적절하고, 패턴만 재사용한다. 나아가 하나의 Python 추상 클래스 계층으로 4개 포맷을 묶는 것도 과하다.

- **XLSX는 resolver가 필요 없다.** `anchor={type:"cell", sheet, cell}`은 이미 결정론적 O(1) 주소라 모호성이 발생할 수 없다. resolver 추상화를 씌우면 불필요한 레이어다.
- **HWP는 Python 프로세스 밖(Node/WASM, `backend/workers/hwp_worker.mjs`)에 이미 resolver 로직이 있다.** `@rhwp/core`의 `searchAllText` + occurrence 기반 `replaceText`로 이미 정밀 치환이 동작한다. Python ABC 계층에 끼워 넣으면 프로세스 경계를 무시한 가짜 추상화가 된다.
- PDF/DOCX만 Python 클래스 구현체가 실익이 있다.

### 5.2 공통 wire contract

고정하는 것은 클래스가 아니라 입출력 shape이다.

공통 resolve 패턴:

```text
읽기순서 원자 단위 나열
  → 후보 매칭
  → 후보 점수화
  → 후보가 하나이고 충분히 확실하면 RESOLVED
  → 여러 개이거나 불확실하면 NEEDS_CONFIRMATION
  → 실제 patch는 포맷별 renderer/patcher가 수행
```

입력 anchor는 순수 dict를 유지한다 (LLM JSON 그대로). 출력은 현재 `ResolveResult`를 포맷 중립화한 shape:

```text
{
  status: RESOLVED | AMBIGUOUS | NOT_FOUND | UNSUPPORTED,
  location: dict | null,      # 포맷별 위치 표현 (아래 5.3)
  matched_text: str,
  resolution_confidence: float,
  reason: str,
  candidates: list[dict]
}
```

현재 `ResolveResult`(status/page/rect/matched_text/confidence/reason/candidates)는 이미 이 계약에 가깝다. PDF 전용 필드인 `page`/`rect`만 `location` dict로 중립화하면 된다.

### 5.3 포맷별 원자 단위와 location 표현

| 포맷 | 원자 단위 | location 표현 | resolver 실행 위치 |
|---|---|---|---|
| PDF | page/token/bbox | `{page, rect}` | Python (`anchor_resolution.py`, 기존) |
| DOCX | paragraph/run/table-cell | `{paragraph_index, run_span}` 또는 `{table_index, row, col}` | Python (신규) |
| HWP | section/paragraph/charOffset | `{section, paragraph, char_offset, length}` | Node/WASM subprocess (기존 `hwp_worker.mjs` 응답을 계약에 맞춤) |
| XLSX | sheet/cell | `{sheet, cell}` | resolver 없음 (anchor가 곧 주소) |

### 5.4 검증 순서

DOCX를 HWP보다 먼저 검증한다. python-docx의 paragraph/run/table 모델이 명확해서 공통 wire contract가 실제로 버티는지 싸게 확인할 수 있다. HWP는 이미 subprocess 안에서 occurrence 정밀 치환이 동작하므로 급하지 않다.

## 6. Patch Contract — envelope 유지, anchor variant 확장

### 6.1 T1/T2를 별도 schema로 나누지 않는다

현재 6개 operation(`replace_cell`, `replace_text`, `annotate`, `set_cell_style`, `set_number_format`, `set_formula`)이 이미 하나의 envelope를 공유한다:

```text
operation_id / format / operation / title / original / replacement
/ reason / confidence / anchor / patch
```

포맷별로 달라지는 것은 `anchor`/`patch` 두 필드뿐이고 이 패턴은 이미 검증됐다. T2 operation도 **새 envelope가 아니라 anchor의 새 variant**로 확장한다. 완전 분리된 T1/T2 schema를 만들면 dispatch/이력/undo 로직이 envelope 레벨과 anchor 레벨 두 군데에서 분기하게 되어 분기 복잡도만 늘어난다.

### 6.2 T2 anchor variant 예시

```json
{
  "operation": "update_table_cell",
  "original": "100,000원",
  "replacement": "150,000원",
  "anchor": {
    "type": "table_cell",
    "table_hint": "지급 내역",
    "row_match": {"label": "합계"},
    "column_match": {"label": "금액"},
    "candidate_source": "docx_table_model"
  }
}
```

### 6.3 candidate_source를 schema에 명시한다

`candidate_source`는 단순 메타데이터가 아니라 **risk_level 계산의 입력**이다. `docx_table_model`처럼 결정론적 소스로 찾은 후보와 `vision_crop` fallback으로 찾은 후보는 LLM confidence가 같아도 실제 신뢰도가 다르므로, `candidate_source`에 따라 risk_level을 강제 상향하는 규칙을 둔다.

PDF의 candidate_source 우선순위:

```text
pdf_token_grid (기존 AnchorResolver token 기반)
  → pdfplumber / camelot 표 감지 (결정론적)
  → vision_crop (fallback, 현재 보류 — 9절)
  → manual_confirmation
```

vision은 기본값이 아니라 결정론적 구조 추출이 실패하거나 모호할 때의 fallback이다.

### 6.4 confidence를 이원화한다

현재 `DocumentChange.confidence`는 LLM의 "이 교체가 의미적으로 맞다는 확신"이고, `ResolveResult.confidence`는 백엔드의 "이 위치가 맞다는 확신"이다. 이 둘은 다른 실패 모드를 나타내므로 하나의 필드로 뭉치면 `NEEDS_CONFIRMATION` UI에서 "왜 확인이 필요한지"(의미가 애매한지, 위치가 애매한지)를 설명할 수 없다.

- `confidence` (기존): LLM의 semantic confidence
- `resolution_confidence` (신규): resolver의 위치 confidence — anchor 해석 결과와 함께 영속화

### 6.5 operation dispatch의 장기 방향

`DocumentChange.operation`은 현재 choices 제약 없는 자유 문자열이며 patcher가 암묵적 문자열 분기로 처리한다. operation 수가 늘어나는 T2 시점에 dispatch table로 명시화한다. 지금 당장은 하지 않는다.

## 7. Render/Structural Validation

원칙 (PDF skill의 render → inspect → operate → re-render/compare 철학 차용):

```text
원본 렌더
  → patch 적용
  → 수정본 렌더
  → 구조적 invariant 검증
  → 통과해야 artifact READY
```

단, 처음부터 pixel diff를 하지 않는다. 폰트 안티에일리어싱/렌더러 차이로 노이즈가 커서 검출력 대비 비용이 나쁘다. 베타 전에는 구조적 invariant 검증만 넣는다.

### 7.1 PDF 최소 invariant (우선순위 순)

1. **(최우선) 수정본에서 `replacement`가 원래 rect 근처에서 텍스트로 재추출되고, `original`은 그 자리에서 사라졌는지.** AnchorResolver의 token 추출 코드를 그대로 재사용하며, PR #30/#31이 고친 버그 클래스를 직접 재검증한다. "검게 칠했는데 아무것도 안 들어간" 케이스 대부분을 잡는다.
2. render 성공(예외 없음), 페이지 수 유지, 예상 밖 빈 페이지 없음 — 사실상 공짜.
3. 같은 페이지에서 RESOLVED된 여러 change의 redact rect끼리 겹치지 않는지 — token gap 임계값(폰트 크기 대비 20%) 오판으로 두 anchor가 충돌 해석되는 케이스를 잡는다.
4. redact/overlay 영역이 페이지 대비 비정상적으로 크지 않은지.

검증 실패 시 artifact를 `READY`로 내보내지 않고 `FAILED`(사유 코드 `render_validation_failed`)로 멈춘다.

### 7.2 DOCX/HWP는 뒤로 미룬다

DOCX/HWP 래스터 검증은 LibreOffice headless 같은 무거운 인프라가 필요하다. PDF에서 구조적 검증의 효과를 먼저 증명한 뒤 확장한다. 1인 메이커 운영 부담 제약에 맞춘 순서다.

## 8. 실패 사유 코드

"생성 실패"와 "위치 확인 필요"를 구분하는 기존 UX를 확장해, 실패 사유를 코드로 고정한다.

| 코드 | 의미 |
|---|---|
| `unsupported_scan` | 스캔 PDF/이미지 문서 — OCR 기반 수정은 베타 후 |
| `ambiguous_anchor` | 후보 다수 또는 resolution_confidence 부족 → `NEEDS_CONFIRMATION` |
| `render_validation_failed` | patch는 적용됐으나 7절 invariant 검증 실패 |
| `patch_failed` | 세부 안정 코드가 없는 patch 실패 |
| `source_file_missing` | 원본 파일 없음 |
| `unsupported_format` | 수정본 생성을 지원하지 않는 포맷 |
| `source_file_read_error` | 원본 파일 읽기 실패 |
| `render_exception` | renderer 경계의 예측하지 못한 실패 |
| `artifact_save_error` | 결과물 storage 저장 실패 |
| `unsupported_layout_edit` | 레이아웃/서식 구조 변경 요청 — T2 범위 |
| `unsupported_table_edit` | 표 구조 변경 요청 — T2 범위 |

patch 실행 결과의 코드는 `DocumentChange.failure_code`와
`DocumentVersion.failure_code`에 영속화한다. API는 이 코드와 backend allowlist에서
생성한 안전한 한국어 `failure_message`만 반환한다. raw `error_message`, exception,
파일 경로, subprocess stderr는 로그와 내부 관측 경계에만 남기고 사용자 API/UI에는
노출하지 않는다. unknown/legacy failed code는 일반 안내로 fallback하고, legacy
`NEEDS_CONFIRMATION`의 빈 code는 상태 의미에 따라 `ambiguous_anchor`로 복구한다.

## 9. 이미지/PII 정책 (미결 — 보류)

T3(및 PDF T2의 vision fallback)에서 page render image나 crop을 LLM에 넘기는 순간, 현재의 PII 방어선이 무력화되는 문제가 있다.

- 현재 `mask_pii()`(`ax-engine/masking/pii_masker.py`)는 순수 문자열 정규식 4종(주민번호/전화번호/계좌번호/이메일) 치환이다. 이미지 픽셀에는 개념적으로 관여할 수 없다.
- 페이지를 래스터화해 보내면 "LLM에는 마스킹된 텍스트만 간다"는 보안 불변식이 깨진다. 이는 제품의 핵심 차별점(자금/인사 데이터 유출 공포 해소)과 정면 충돌한다.

검토된 옵션 (2026-07-10 논의, 결정 보류):

1. **이미지 전송 자체를 하지 않는다** — T2/T3도 token bbox·표 경계 후보 같은 구조화된 JSON만 전달. 보안 불변식 유지, 대신 순수 시각 판단 정확도 한계.
2. **RAG 양식(blank template)만 이미지 허용** — 빈 서식은 값이 없어 PII 원천 차단. 실사용 문서는 구조 메타데이터만. RAG ingestion 시점에 blank 검증 게이트 필요.
3. **사전 redaction crop만 허용** — `pii_masker` 정규식 매치를 token bbox에 매핑해 화이트박스 처리 후 래스터화. 기존 `_apply_pdf_redact_overlay` 인프라 재사용 가능하나, born-digital 텍스트 레이어가 없는 스캔/서명/도장은 커버 불가.

구조적 완화 지점: RAG에 저장하는 "양식 자체"(blank template)와 사용자가 채워서 업로드한 실사용 문서는 PII 위험도가 본질적으로 다르다. 이 구분이 옵션 2의 근거다.

이 결정 전까지 vision 계열 candidate_source는 구현하지 않는다.

## 10. 베타 전 최소 범위 / 베타 후 확장

### 10.1 베타 전

- T1 `replace_text` 안정화 (PDF readable text 짧은 치환)
- **DOCX 다중 매치 침묵 처리 수정**: 현재 DOCX `replace_text`는 target_text가 포함된 첫 번째 단락만 조용히 수정하고 다중 매치 감지가 없다 (`patcher.py`의 substring 순회). 같은 문구가 두 번 나오면 PDF처럼 멈추지 않고 첫 번째만 바꾼다 — PR #31 이전 PDF보다 못한 상태. resolver 추상화 없이 기존 `NEEDS_CONFIRMATION` 패턴만 재사용해 "매치 2개 이상이면 멈춤"으로 고친다. 이것은 T2 준비가 아니라 T1 안정화 범위의 결함 수정이다.
- expected_context 기반 ambiguity 처리 유지, `NEEDS_CONFIRMATION` UX 유지
- CJK redaction/overlay 회귀 방어 (PR #29 회귀 테스트 유지)
- PDF 구조적 render validation smoke check (7.1절 invariant 1~2)
- 실패 사유 코드 정리 (8절)
- Patch Contract 확장 방향 확정 (6절 — envelope 유지 + anchor variant)

### 10.2 베타 후

- `TargetResolver` wire contract 정식화와 DOCX resolver 클래스화 (5절)
- DOCX 표 내부 텍스트 탐색: 현재 `doc.paragraphs` 순회는 표 셀 단락을 포함하지
  않아, 같은 문구가 본문 1회 + 표 안 1회 나오면 다중 매치로 감지되지 않고 본문만
  수정된다 — DOCX resolver 클래스화 시 표 셀 순회를 함께 넣는다
- HWP subprocess 응답을 wire contract에 맞춤
- PDF 표 감지 (pdfplumber/camelot) 기반 T2 candidate_source
- T2 operation (`update_table_cell`, 행/열 삽입 등 — 구조 수정 보류 해제 논의 포함)
- 7.1절 invariant 3~4, DOCX/HWP 렌더 검증
- 이미지/PII 정책 결정 (9절) 후 vision fallback
- 스캔 PDF OCR 기반 수정, 차트/도표 생성, multi-page reflow, 완전 자동 양식 기반 문서 생성

## 11. 확장성 스트레스 테스트 — T2 구조 변경 / T3 생성

이 구조가 어디까지 버티는지 미리 점검한 결과.

### 11.1 그대로 버티는 범위

값 계열 T2 — 라벨-값 필드 채우기, 표 셀 수정. anchor variant(`table_cell` 등)와 `candidate_source` 추가만으로 확장되며, envelope/resolver wire contract/validation/버전 파이프라인을 전부 재사용한다. 6절 설계가 정확히 이 범위를 겨냥한다.

### 11.2 보강이 필요한 세 지점

**(1) envelope의 치환 중심 의미론.**
`original`/`replacement`는 값 교체를 전제한다. 행/열 삽입, 표 추가, 차트 삽입은 `original`이 존재하지 않고 삽입할 내용 payload가 필요하다. envelope 자체는 유지하되:

- `original`을 삽입 계열 operation에서 nullable로 완화하고, 삽입 내용은 기존 `patch` JSONField에 담는다 (이미 escape hatch로 존재).
- 7절 validation invariant를 operation 계열별 세트로 재정의한다. 치환 계열: replacement 재추출 + original 소멸 검증. 삽입 계열: 행/열/객체 개수 증가 + **기존 셀/텍스트 불변 검증**. 삽입은 치환과 달리 재적용 시 중복 삽입되는 비멱등 연산이므로 적용 이력 가드도 계열별로 다르다.

**(2) 구조 변경 operation의 순서 의존성과 anchor 무효화.**
행 삽입은 같은 문서 안의 뒤 operation이 가리키는 셀 주소/위치를 바꾼다. 현재 모델은 change 단위 독립 적용(사용자가 일부만 승인 가능)을 전제하므로, 비가환 operation이 들어오면 이 전제가 깨진다. 두 가지 방향이 있고 T2 구조 op 착수 전에 결정해야 한다:

- (a) **apply 시점 re-resolve**: anchor 해석을 plan 생성 시점이 아니라 각 operation 적용 직전에 현재 버전 기준으로 실행. wire contract(5절)가 이미 이 방향과 호환된다 — resolve가 적용 시점에 실행되면 주소 이동이 자연 흡수된다.
- (b) **operation group**: 의존 관계가 있는 operation들("행 삽입 → 그 행의 셀 채우기")을 묶어 전체 승인/전체 거절 단위로 취급.

파생 관찰: 이 지점에서 5.1절의 "XLSX는 resolver가 필요 없다" 판단도 약화된다. 절대 주소 anchor(`{sheet, cell}`)는 구조 변경 후 stale해지므로, T2 구조 변경을 도입하면 XLSX도 label 기반 resolve가 필요해질 수 있다. 다만 클래스 계층이 아닌 wire contract 방식이라 XLSX resolver 구현체를 나중에 추가하는 것으로 흡수 가능하다 — 이것이 contract 기반 설계를 택한 이유이기도 하다.

**(3) T3 생성의 환원 가능 범위.**
문서 생성을 "빈 문서에서의 창조"가 아니라 **"RAG 템플릿 복사 → fill 계열 PatchPlan 적용"으로 환원**하면, 기존 파이프라인(resolver/검증/DocumentVersion/artifact)을 전부 재사용한다. 양식 기반 생성(입력란/날짜란/서명란 채우기)은 이 환원 안에 들어온다.

이 환원이 가능한 범위까지가 현 구조의 자연스러운 확장 한계다. 자유 레이아웃 생성(임의 위치에 표/차트 신규 배치, 레이아웃 재구성)은 anchor를 "수정 대상"이 아닌 "삽입 기준점"으로 재해석하는 별도 operation 계열이 필요하며, 이때 9절 이미지/PII 정책 결정이 선행 조건이 된다.

### 11.3 결론

- 값 계열 T2: 현 구조 그대로 확장 가능.
- 구조 변경 T2: envelope는 유지 가능하나 invariant 계열화(11.2-1)와 순서 의존성 결정(11.2-2)이 선행되어야 한다.
- 양식 기반 T3 생성: 템플릿 환원으로 현 구조에 수렴.
- 자유 레이아웃 T3: 현 구조 밖 — 별도 operation 계열 + 이미지/PII 정책 결정 필요.

## 12. 미결정 사항

| 항목 | 상태 | 결정 시점 |
|---|---|---|
| 이미지/PII 정책 (9절 옵션 1~3) | 보류 | T3 또는 PDF vision fallback 착수 전 |
| T2 구조 수정 보류 해제 여부 | 보류 (2026-07-01 결정 유지) | 베타 인터뷰 결과 반영 |
| 구조 변경 op 순서 의존성 처리 (11.2-2의 a/b) | 방향 2개 식별 | T2 구조 op 착수 전 |
| operation dispatch table 명시화 | 방향만 합의 | T2 operation 추가 시점 |
| HWP location 표현 상세 | 미착수 | DOCX resolver 검증 후 |
