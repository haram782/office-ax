# Office-AX 문서 수정 AX 다음 구현 로드맵 v1

문서 상태: 현재 문서 수정 AX 구현 순서의 기준 문서. MVP 전체 범위와 과금/사용량 갭은 `mvp-scope-and-gap-v1-ko.md`를 우선한다.

관련 문서:

- `mvp-scope-and-gap-v1-ko.md`: MVP 전체 범위, 과금/사용량 측정, 대시보드 갭, 운영자 조회 도구를 함께 다룬다.

## 1. 문서의 목적

이 문서는 `Office-AX 문서 양식 수정 AX v1` 이후의 구현 방향을 정리한다.

기존 v0는 문서 업로드, AI 수정 제안, 적용/거절, artifact 버전 생성까지의 기본 루프를 만들었다.

기존 v1은 XLSX `set_cell_style`을 통해 Office-AX가 단순 텍스트 치환기가 아니라 문서의 양식까지 수정할 수 있음을 증명했다.

이 문서의 목적은 다음 단계에서 무엇을 구현해야 Office-AX가 "AI 문서 수정 제품"으로 더 강해지는지 큰 흐름을 고정하는 것이다.

구현 프롬프트나 작업 티켓은 이 문서를 기준으로 별도로 쪼갠다.

## 2. 현재 기준선

현재 Office-AX의 문서 수정 구조는 다음과 같다.

- 사용자가 문서를 업로드한다.
- LLM이 `PatchPlan`을 생성한다.
- 백엔드가 `DocumentChange`로 변경 제안을 저장한다.
- 사용자가 제안을 적용하거나 거절한다.
- patcher가 승인된 변경만 실제 파일에 적용한다.
- 결과 파일은 `DocumentVersion` artifact로 저장된다.
- 뷰어와 제안 카드에서 수정 위치와 변경 내용을 확인한다.

현재 강점:

- 일반 LLM 채팅과 달리 실제 파일 수정본을 생성한다.
- 변경 제안을 구조화하고 적용/거절할 수 있다.
- artifact와 버전이 남아 감사 가능성이 있다.
- XLSX의 셀 값, 셀 서식 수정까지 확장되었다.

현재 한계:

- XLSX 외 포맷의 양식 수정은 아직 제한적이다.
- XLSX도 표시 형식, 수식, 구조 변경은 아직 제한적이다.
- LLM이 어떤 operation을 언제 생성해야 하는지 아직 더 정교화해야 한다.
- 사용자가 "문서가 실제로 좋아졌다"고 느낄 수 있는 업무 시나리오 테스트가 부족하다.

## 3. 제품 방향

Office-AX는 "문서를 대신 작성해주는 챗봇"이 아니라 "문서 작업 흐름을 수정 가능한 산출물로 바꾸는 AX"가 되어야 한다.

따라서 다음 구현의 중심은 단순히 operation 수를 늘리는 것이 아니다.

핵심은 다음 세 가지다.

1. 사용자가 실제로 자주 요청하는 업무 문서 수정을 지원한다.
2. LLM이 만든 계획을 서버가 검증 가능한 방식으로 적용한다.
3. 결과물이 원본 문서의 맥락, 양식, 버전 이력을 보존한다.

## 4. 경쟁 제품 대비 포지션

Microsoft 365 Copilot, Claude for Excel, Gemini in Sheets 같은 제품은 Office 또는 스프레드시트 안에서 AI를 호출하는 방향으로 발전하고 있다.

Office-AX가 이들과 정면으로 "더 좋은 Excel AI" 경쟁을 하는 것은 좋지 않다.

Office-AX의 차별점은 다음이어야 한다.

- HWP, PDF, XLSX 등 한국 업무 문서 흐름을 함께 다룬다.
- 사용자가 Microsoft 365 테넌트나 특정 앱 안에 들어가지 않아도 된다.
- 파일 수정 과정을 `PatchPlan`, `DocumentChange`, `DocumentVersion`으로 추적한다.
- LLM 답변이 아니라 검증된 수정본 artifact를 만든다.
- 문서 하나가 아니라 여러 문서, 이메일, 참조 자료로 확장할 수 있다.

제품 메시지는 다음에 가깝다.

```text
Copilot은 Office 안에서 일한다.
Office-AX는 회사 문서 흐름 전체를 검증 가능한 수정본으로 남긴다.
```

## 5. 다음 구현 원칙

### 5.1 XLSX를 먼저 깊게 판다

여러 포맷을 얕게 넓히는 것보다 XLSX 하나에서 "이 정도면 실제 업무 문서를 고친다"는 감각을 만드는 것이 우선이다.

이유:

- `openpyxl` 기반 구현 가능성이 높다.
- 셀, range, 표시 형식, 수식, 행/열 구조가 비교적 명확하다.
- 중소기업 업무 문서에서 XLSX 비중이 크다.
- 테스트 자동화가 쉽다.

### 5.2 Patch operation은 검증 가능한 것부터 늘린다

LLM이 할 수 있어 보이는 것과 서버가 안전하게 적용할 수 있는 것은 다르다.

새 operation은 다음 조건을 만족해야 한다.

- anchor를 명확히 표현할 수 있다.
- 적용 전 문서 상태를 검증할 수 있다.
- 실패 시 개별 `DocumentChange` 실패로 격리할 수 있다.
- artifact 생성 후 자동 테스트로 결과를 확인할 수 있다.

### 5.3 전체 재생성은 별도 트랙으로 둔다

"이 문서를 회사 양식으로 다시 작성해줘"는 patch보다 regenerate에 가깝다.

다음 구현 로드맵에서는 부분 수정 patch를 우선한다.

전체 재생성은 다음 요소가 준비된 뒤 별도 기획으로 다룬다.

- 템플릿 모델
- 문서 생성 렌더러
- 원본과 생성본의 diff/검토 UX
- 새 문서의 출처 추적

## 6. 구현 단계

### Phase 1. 안정화 작업

목표:

현재 문서 수정 루프의 확실한 버그와 운영 리스크를 먼저 닫는다.

작업:

- PDF `redact_overlay` 한글 폰트 버그 수정
- 한글 replacement 보존 회귀 테스트 추가
- 기존 XLSX `set_cell_style` E2E 테스트 재확인
- artifact 생성/다운로드 경로의 멱등성 유지 확인

성공 기준:

- 한글 PDF 수정 텍스트가 깨지지 않는다.
- 기존 문서 앱 테스트가 통과한다.
- 새 기능 확장 전에 기존 루프가 신뢰 가능한 상태다.

비범위:

- PDF 구조 수정
- PDF 레이아웃 재생성
- 다국어 CJK 자동 분기

### Phase 2. XLSX 표시 형식 수정

목표:

날짜, 금액, 퍼센트 같은 업무 문서의 표시 형식을 AI가 수정할 수 있게 한다.

새 operation:

```text
set_number_format
```

예상 사용자 요청:

```text
금액 열은 천 단위 콤마와 원 표시를 붙여줘.
날짜는 YYYY-MM-DD 형식으로 통일해줘.
비율 열은 소수점 한 자리 퍼센트로 표시해줘.
```

필수 설계:

- `anchor.type = cell_range`
- `expected_context` 필수
- `patch.number_format` 필수
- number format whitelist 사용
- range 최대 크기 제한 유지

초기 허용 후보:

- `yyyy-mm-dd`
- `yyyy. mm. dd`
- `#,##0`
- `#,##0원`
- `#,##0.00`
- `0.0%`
- `0.00%`

성공 기준:

- artifact를 열었을 때 실제 셀 표시 형식이 바뀐다.
- 기존 값은 손상되지 않는다.
- 잘못된 context나 허용되지 않은 format은 개별 change 실패로 기록된다.
- ChangeSuggestionCard에서 텍스트 diff가 아니라 표시 형식 변경 요약이 보인다.

### Phase 3. XLSX 수식 설정

목표:

사용자가 요청한 합계, 평균, 개수 같은 간단한 계산을 문서에 반영할 수 있게 한다.

새 operation:

```text
set_formula
```

예상 사용자 요청:

```text
합계 행에 금액 합계를 넣어줘.
평균 단가를 계산해줘.
총 건수를 계산해줘.
```

1차 범위:

- 단일 셀 수식 설정
- range 전체 수식 적용은 제외
- 허용 함수 whitelist 사용

초기 허용 함수 후보:

- `SUM`
- `AVERAGE`
- `COUNT`
- `COUNTA`
- `MIN`
- `MAX`
- `IF`

금지:

- 외부 파일 참조
- URL
- 매크로
- `INDIRECT`
- `HYPERLINK`
- `WEBSERVICE`
- 알 수 없는 함수

성공 기준:

- artifact에서 대상 셀에 수식이 저장된다.
- openpyxl로 수식 문자열을 확인할 수 있다.
- 금지 함수나 외부 참조는 실패 처리된다.
- ChangeSuggestionCard에서 수식 설정 요약이 보인다.

### Phase 4. LLM PatchPlan 프롬프트 정교화

목표:

LLM이 operation을 무리하게 만들지 않고, 사용자의 의도에 맞는 검증 가능한 PatchPlan을 생성하게 한다.

추가할 operation:

- `set_cell_style`
- `set_number_format`
- `set_formula`

프롬프트 원칙:

- 사용자가 명시적으로 요청한 범위 안에서만 서식/표시 형식/수식 operation을 만든다.
- 불확실하면 operation을 만들지 않는다.
- 모든 XLSX 양식 operation에는 `expected_context`를 포함한다.
- range는 과도하게 넓히지 않는다.
- 설명은 사용자가 적용/거절 판단을 할 수 있게 쓴다.

테스트 시나리오:

- "표 헤더 보기 좋게 정리해줘"
- "날짜 표시 형식 통일해줘"
- "금액 열에 원 표시 붙여줘"
- "합계 행 만들어줘" 중 수식 설정까지만 가능한 케이스
- 애매한 요청에서 operation을 생성하지 않는 케이스

성공 기준:

- LLM 출력 JSON이 schema를 통과한다.
- expected_context 누락률이 낮다.
- patcher 실패가 예측 가능한 validation failure로 남는다.

### Phase 5. XLSX 업무 시나리오 E2E

목표:

기능 단위 테스트를 넘어 실제 사용자가 느끼는 문서 수정 루프를 검증한다.

대표 시나리오:

```text
업로드된 매출표에서
1. 헤더를 강조하고
2. 금액 열 표시 형식을 정리하고
3. 합계 셀에 수식을 넣고
4. 수정본을 다운로드한다.
```

테스트 흐름:

- UploadLog 생성
- original DocumentVersion 생성
- PatchPlan 생성 또는 mock
- DocumentChange 저장
- apply
- patch trigger
- artifact 생성
- 다운로드
- openpyxl로 결과 검증

성공 기준:

- 한 파일에서 여러 operation이 함께 적용된다.
- 일부 operation 실패 시 나머지 성공 operation은 유지된다.
- artifact와 version 상태가 일관된다.
- 사용자가 UI에서 어떤 변경이 적용됐는지 이해할 수 있다.

## 7. 후속 단계

### 7.1 XLSX 구조 수정

후보 operation:

- `insert_table_row`
- `insert_table_column`
- `copy_row_style`
- `merge_cells`

핵심 리스크:

- 행/열 삽입 시 anchor가 이동한다.
- 여러 change를 동시에 적용하면 순서에 따라 결과가 달라질 수 있다.
- range overlap 충돌 감지가 필요하다.

선행 설계:

- operation 적용 순서
- anchor 재계산
- 충돌 판정
- 삽입 기준 행/열의 expected_context

이 단계는 다음 구현 묶음에 바로 넣지 않는다.

### 7.2 DOCX 제한 진입

첫 목표:

- 표 셀 텍스트 변경
- 제한적 문단 정렬
- 제한적 bold 처리

주의:

- `python-docx`는 실제 렌더링 엔진이 아니다.
- 복잡한 회사 양식 정리는 patch보다 regenerate에 가깝다.
- DOCX는 먼저 "안전한 부분 수정" 범위를 좁게 잡아야 한다.

### 7.3 HWP POC

HWP는 한국 시장에서 중요하지만 기술 리스크가 크다.

선행 POC:

- 표 셀 탐색
- 표 셀 텍스트 변경
- 저장 후 한글에서 정상 열림 확인
- Node worker 안정성 확인
- 실패/타임아웃 격리

표 구조 변경은 POC 성공 후에만 검토한다.

### 7.4 regenerate 트랙

별도 제품 트랙으로 분리한다.

대상 요청:

- 회사 양식으로 전체 재작성
- 보고서 초안 생성
- 여러 문서 내용을 합쳐 새 문서 생성
- 템플릿 기반 문서 생성

필요 요소:

- 템플릿 관리
- 문서 생성 렌더러
- 출처 추적
- 생성본 검토 UX

## 8. UX 방향

문서 수정 AX의 UI는 "채팅 답변"보다 "수정 제안 검토"에 가까워야 한다.

ChangeSuggestionCard는 operation별 표시 방식을 가져야 한다.

표시 예:

- `replace_cell`: 원래 값 -> 수정 값
- `set_cell_style`: 굵게, 배경색, 정렬, 테두리
- `set_number_format`: 표시 형식 변경
- `set_formula`: 수식 설정
- `insert_table_row`: 행 삽입 위치와 삽입 내용

사용자에게 중요한 정보:

- 어디를 바꾸는가
- 무엇을 바꾸는가
- 왜 바꾸는가
- 적용하면 파일이 어떻게 달라지는가
- 실패했다면 왜 실패했는가

## 9. 테스트 전략

테스트는 operation마다 네 층으로 둔다.

### 9.1 Validation test

schema와 patch whitelist가 잘못된 입력을 막는지 확인한다.

예:

- missing expected_context
- invalid range
- oversized range
- invalid format
- forbidden formula

### 9.2 Patcher test

실제 파일 bytes에 operation이 적용되는지 확인한다.

예:

- openpyxl로 artifact를 다시 열어 셀 스타일/표시 형식/수식 확인
- 실패 change가 failed_items에 남는지 확인

### 9.3 API test

DocumentChange 저장, apply, patch trigger, DocumentVersion artifact 저장 흐름을 확인한다.

### 9.4 UI test

ChangeSuggestionCard가 operation별로 올바르게 표시되는지 확인한다.

## 10. 구현 우선순위

권장 순서:

1. PDF CJK 폰트 버그 수정
2. XLSX `set_number_format`
3. XLSX `set_formula`
4. LLM PatchPlan 프롬프트 정교화
5. XLSX 업무 시나리오 E2E
6. XLSX 구조 수정 설계
7. DOCX 제한 POC
8. HWP 표 POC
9. regenerate 별도 기획

이 순서는 구현 난도와 제품 체감의 균형을 기준으로 한다.

## 11. 이번 장시간 구현 묶음의 권장 범위

자리 비운 동안 오래 돌릴 구현 묶음은 다음으로 제한한다.

포함:

- PDF CJK 폰트 버그 수정
- XLSX `set_number_format`
- XLSX `set_formula`
- 관련 schema/prompt/frontend/test 업데이트
- XLSX E2E 테스트 보강

제외:

- XLSX 행/열 삽입
- DOCX/HWP/PPTX 양식 수정
- PDF 구조 수정
- regenerate
- 템플릿 관리

이 범위가 좋은 이유:

- 이미 확정된 patcher 구조를 재사용한다.
- 모델 변경 없이 `DocumentChange.operation`, `anchor`, `patch`로 확장 가능하다.
- 사용자 체감이 크다.
- 테스트 자동화가 가능하다.
- 제품 결정을 새로 많이 요구하지 않는다.

## 12. 완료 기준

다음 조건을 만족하면 이번 로드맵의 첫 구현 묶음은 완료로 본다.

- 한글 PDF replacement가 깨지지 않는다.
- XLSX에서 셀 값, 셀 서식, 표시 형식, 수식 설정이 모두 가능하다.
- 각 operation은 expected_context 검증을 통과해야만 적용된다.
- 실패한 operation은 전체 patch를 깨뜨리지 않고 개별 실패로 남는다.
- 사용자는 UI에서 operation별 변경 내용을 이해할 수 있다.
- artifact 다운로드 후 실제 Office 파일에서 변경이 확인된다.
- backend/frontend 핵심 테스트가 통과한다.

## 13. 남은 제품 질문

아래 질문은 다음 기획 라운드에서 결정한다.

- 사용자가 "합계 행을 추가해줘"라고 했을 때 `set_formula`만 제안할지, `insert_table_row`까지 기다릴지
- XLSX range overlap 충돌을 언제부터 정교하게 감지할지
- DOCX/HWP를 어느 수준부터 "지원"이라고 표현할지
- regenerate 결과물을 기존 문서의 버전으로 볼지, 새 문서로 볼지
- 템플릿 기반 문서 생성은 파이프라인 자동화와 어떻게 연결할지

## 14. 한 줄 요약

다음 구현의 핵심은 XLSX를 중심으로 "값을 바꾸는 AI"에서 "업무 문서의 표시, 계산, 양식까지 검증 가능하게 고치는 AX"로 올라서는 것이다.
