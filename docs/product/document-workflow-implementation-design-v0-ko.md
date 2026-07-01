# Office-AX 문서 수정 및 업무 흐름 추론 구현 설계 v0

문서 상태: v0 구현 설계 및 장기 workflow inference 배경 문서. 현재 MVP 범위는 `mvp-scope-and-gap-v1-ko.md`, 현재 PatchPlan 계약은 `patch-plan-schema-v0-ko.md`를 우선한다.

## 1. 목적

이 문서는 `viewer-first-workflow-automation-v0-ko.md`의 제품 방향을 구현 가능한 시스템 설계로 내린다.

구현 목표는 두 가지다.

1. AI 문서 수정 결과를 뷰어가 소비할 수 있는 구조화된 데이터로 만든다.
2. 사용자의 문서 작업 이벤트를 기록해 반복 업무 흐름을 추론하고, 파이프라인 초안으로 연결한다.

중요한 원칙:

- 처음부터 완전한 자동 실행 엔진을 만들지 않는다.
- 먼저 문서 수정 제안, 하이라이트, 적용/거절, 다운로드 경험을 완성한다.
- 동시에 workflow inference에 필요한 이벤트를 쌓기 시작한다.
- 파이프라인은 빈 캔버스가 아니라 추론된 후보를 다듬는 편집기로 발전시킨다.

## 2. 현재 코드에서 이어받을 기반

현재 repo에는 이미 활용 가능한 뼈대가 있다.

### Backend

- `UploadLog`: 업로드된 문서와 분석 결과 저장
- `ChatSession`, `ChatMessage`: 워크스페이스 채팅과 파일 연결
- `ChatMessage.snippet_data`: 파일별 인라인 프리뷰 및 수정 데이터 저장
- `UserActionLog`: 행동 로그 및 패턴 감지 고도화 기반
- `change_highlights`: 프론트 뷰어가 사용할 하이라이트 계약의 초기 형태
- `IngestionWorkflow`: 기존 패턴 감지/인바운드 이메일 자동화의 레거시 기반
- `Pipeline`, `PipelineStep`: 파이프라인/스텝 API 기반

### Frontend

- `Workspace/index.jsx`: 3열 워크스페이스 구조
- `WorkspaceCenter`: 중앙 문서 뷰어
- `WorkspaceChat`: 우측 채팅
- `WorkspaceSidebar`: 대화/파일/규칙 영역
- `DocumentPanel`: 문서 포맷별 프리뷰 및 파일 아이템 처리
- `snippetData`, `change_highlights`, `highlightedCells`: 변경 위치 표시의 초기 데이터 흐름

### AX Engine

- `analyze_document`: 문서 파싱, LLM 호출, 결과 콜백
- `parsers/*`: 포맷별 텍스트/구조 추출
- `DOCUMENT_ANALYSIS_PROMPT`: 분석 프롬프트
- `AnalysisResult`: LLM 응답 래퍼

설계 방향은 새 시스템을 별도로 만들기보다, 위 기반을 v1 계약으로 확장하는 것이다.

## 3. 핵심 아키텍처

```text
Frontend Workspace
  -> Backend Chat/File API
  -> AX Engine analyze/edit task
  -> Structured Edit Suggestions
  -> Backend stores ChatMessage + DocumentChange + ActivityEvent
  -> Frontend renders highlights and suggestion cards
  -> User applies/rejects/downloads
  -> ActivityEvent accumulates
  -> WorkflowCandidate inferred
  -> PipelineDraft / PipelineStep generated
```

초기에는 `DocumentChange`, `ActivityEvent`, `WorkflowCandidate`를 명시 모델로 추가하는 방향이 좋다.

`ChatMessage.snippet_data`만으로 모든 상태를 관리하면 빠르게 시작할 수는 있지만, 적용/거절/반복 추론/파이프라인 변환까지 가면 상태 관리가 불안정해진다.

## 4. Structured Edit Suggestion Schema v1

LLM은 일반 텍스트 답변만 반환하면 안 된다. 뷰어와 백엔드가 사용할 수 있는 구조화된 수정 제안을 반환해야 한다.

### Top-level

```json
{
  "version": "edit_suggestion.v1",
  "source_type": "hwp",
  "summary": "문서 검토를 완료했습니다.",
  "detected_issues": [],
  "edit_suggestions": [],
  "risk_notes": [],
  "output_requests": [],
  "model_used": "gpt-4.1",
  "tokens": {
    "input": 12000,
    "output": 1800
  }
}
```

### EditSuggestion

```json
{
  "id": "sug_001",
  "change_type": "date_format",
  "severity": "warning",
  "title": "날짜 표기 형식 통일",
  "original": "2025년 08월 11일",
  "replacement": "2025-08-11",
  "reason": "문서 내 날짜 표기를 YYYY-MM-DD 형식으로 통일합니다.",
  "confidence": 0.86,
  "anchor": {
    "type": "text_match",
    "target_text": "2025년 08월 11일",
    "context_before": "신청일시",
    "context_after": "무주택기간",
    "page": 1,
    "paragraph_index": 12
  },
  "apply": {
    "mode": "replace_text",
    "requires_confirmation": false
  }
}
```

### XLSX anchor

```json
{
  "anchor": {
    "type": "cell",
    "sheet": "Sheet1",
    "cell": "D12",
    "row_index": 12,
    "col_index": 4
  },
  "apply": {
    "mode": "set_cell_value",
    "value": "15000"
  }
}
```

### HWP anchor

```json
{
  "anchor": {
    "type": "text_match",
    "target_text": "무주택기간 3년이상",
    "context_before": "청약신청 정보",
    "context_after": "혼인여부",
    "section_title": "청약신청 정보",
    "paragraph_index": 8
  },
  "apply": {
    "mode": "replace_text",
    "requires_confirmation": true
  }
}
```

HWP v0에서는 좌표 정확도보다 다시 찾을 수 있는 anchor가 중요하다.

## 5. change_highlights v1

기존 `backend/apps/chat/change_highlights.py`의 계약을 유지하되, `edit_suggestions`와 1:1로 연결되도록 확장한다.

권장 필드:

```json
{
  "id": "highlight_sug_001",
  "suggestion_id": "sug_001",
  "kind": "correction",
  "target": "text",
  "format": "hwp",
  "severity": "warning",
  "status": "pending",
  "original": "2025년 08월 11일",
  "corrected": "2025-08-11",
  "summary": "날짜 표기 형식 통일",
  "anchor": {
    "type": "text_match",
    "target_text": "2025년 08월 11일",
    "context_before": "신청일시",
    "context_after": "무주택기간"
  },
  "source": "llm_suggestion"
}
```

기존 XLSX/PPTX 필드는 유지한다.

- `cell`, `sheet`
- `slide_index`, `shape_index`
- `row_index`, `col_index`

프론트는 `target`과 `format`을 기준으로 렌더러를 선택한다.

## 6. Backend 모델 설계

### DocumentChange

AI가 제안한 문서 변경 단위.

위치:

```text
backend/apps/documents/models.py
```

또는 변경 도메인을 분리하려면:

```text
backend/apps/document_changes/
```

권장 필드:

```text
DocumentChange
  user              FK User
  session           FK ChatSession null
  upload_log        FK UploadLog
  source_message    FK ChatMessage null
  suggestion_id     CharField
  source_type       CharField
  change_type       CharField
  severity          CharField
  title             CharField
  original          TextField
  replacement       TextField
  reason            TextField
  confidence        FloatField
  anchor            JSONField
  apply_payload     JSONField
  status            pending / applied / rejected / superseded / failed
  applied_at        DateTime null
  rejected_at       DateTime null
  created_at
  updated_at
```

인덱스:

```text
(user, upload_log, status)
(user, created_at)
(upload_log, suggestion_id) unique
```

### ActivityEvent

workflow inference를 위한 이벤트 로그.

기존 `UserActionLog`를 확장할 수도 있지만, 이벤트 종류가 많아지므로 장기적으로는 별도 모델이 더 명확하다.

v0에서는 `UserActionLog.ActionType`과 `meta`를 확장해 시작하고, v1에서 `ActivityEvent`로 분리해도 된다.

권장 별도 모델:

```text
ActivityEvent
  user              FK User
  session           FK ChatSession null
  upload_log        FK UploadLog null
  document_change   FK DocumentChange null
  event_type        CharField
  file_type         CharField
  document_role     CharField blank
  intent            CharField blank
  task_run_key      CharField blank
  payload           JSONField
  created_at
```

초기 event_type:

```text
document_uploaded
document_opened
reference_selected
prompt_submitted
llm_response_generated
edit_suggestion_generated
edit_suggestion_applied
edit_suggestion_rejected
output_generated
file_downloaded
message_copied
automation_suggestion_shown
automation_suggestion_accepted
automation_suggestion_dismissed
```

### WorkflowCandidate

반복 업무 흐름 후보.

```text
WorkflowCandidate
  user              FK User
  title             CharField
  status            suggested / accepted / dismissed / converted_to_pipeline
  confidence        FloatField
  repeated_count    PositiveInteger
  observed_steps    JSONField
  evidence          JSONField
  missing_context_questions JSONField
  pipeline          FK Pipeline null
  first_seen_at
  last_seen_at
  created_at
  updated_at
```

### PipelineDraft

초기에는 별도 모델 없이 `Pipeline(is_active=False)` + `PipelineStep`으로 초안을 표현해도 된다.

단, 사용자가 수락하기 전 임시 후보와 정식 파이프라인을 분리하고 싶다면 `PipelineDraft`를 둔다.

v0 권장:

```text
WorkflowCandidate.accepted
-> Pipeline 생성
-> PipelineStep 생성
-> candidate.pipeline 연결
```

## 7. Backend API 설계

### 변경 제안 조회

```text
GET /api/v1/uploads/{upload_id}/changes/
```

응답:

```json
[
  {
    "id": 1,
    "suggestion_id": "sug_001",
    "status": "pending",
    "change_type": "date_format",
    "title": "날짜 표기 형식 통일",
    "original": "2025년 08월 11일",
    "replacement": "2025-08-11",
    "reason": "...",
    "anchor": {},
    "apply_payload": {}
  }
]
```

### 변경 적용

```text
POST /api/v1/document-changes/{id}/apply/
```

v0 동작:

- DB status를 `applied`로 변경
- 가능하면 artifact 생성 작업 enqueue
- ActivityEvent 기록

XLSX는 실제 셀 변경 artifact까지 목표로 한다.

HWP는 v0에서 status 적용과 UI 반영까지만 하고, 실제 patch는 후속 단계로 둘 수 있다.

### 변경 거절

```text
POST /api/v1/document-changes/{id}/reject/
```

동작:

- DB status를 `rejected`로 변경
- ActivityEvent 기록

### 전체 적용

```text
POST /api/v1/uploads/{upload_id}/changes/apply-all/
```

필터:

- `change_type`
- `severity`
- `requires_confirmation=false`만 적용

### 이벤트 기록

```text
POST /api/v1/activity-events/
```

프론트에서 직접 기록해야 하는 이벤트:

- document_opened
- reference_selected
- file_downloaded
- message_copied

백엔드에서 자동 기록하는 이벤트:

- document_uploaded
- prompt_submitted
- llm_response_generated
- edit_suggestion_generated
- edit_suggestion_applied
- edit_suggestion_rejected
- output_generated

### 자동화 후보

```text
GET /api/v1/workflow-candidates/
POST /api/v1/workflow-candidates/{id}/accept/
POST /api/v1/workflow-candidates/{id}/dismiss/
POST /api/v1/workflow-candidates/{id}/convert-to-pipeline/
```

`convert-to-pipeline`은 `Pipeline`과 `PipelineStep`을 만든다.

## 8. AX Engine 설계

### 작업 분리

현재 `analyze_document`는 분석 중심이다. v0에서는 기존 태스크를 확장할 수 있지만, 장기적으로는 다음처럼 분리하는 것이 좋다.

```text
tasks.analyze_document
  - 요약, 오류 탐지, 기본 분석

tasks.suggest_document_edits
  - 구조화된 edit_suggestions 생성

tasks.apply_document_changes
  - 포맷별 artifact 생성
```

초기에는 `analyze_document` 결과에 `edit_suggestions`와 `change_highlights`를 추가하는 방식으로 시작한다.

### LLM 프롬프트 요구사항

프롬프트는 반드시 다음을 강제한다.

- 한국어 업무 문서 기준으로 판단
- JSON만 반환
- `edit_suggestions` 배열 반환
- 각 suggestion은 anchor를 포함
- 확실하지 않은 위치는 `requires_confirmation=true`
- 실제로 찾을 수 없는 내용은 만들지 않음
- 개인정보는 원문 전체를 노출하지 않고 필요한 범위만 마스킹

### LLM 응답 검증

LLM 응답은 바로 저장하지 말고 검증한다.

검증 항목:

- JSON parse 가능
- version 일치
- 필수 필드 존재
- confidence 범위 0~1
- source_type 허용값
- change_type 허용값
- anchor type 허용값
- original/replacement 길이 제한

검증 실패 시:

- 사용자에게 일반 분석 답변만 제공
- 구조화 제안은 저장하지 않음
- ActivityEvent에 validation_failed 기록

## 9. 포맷별 구현 전략

### XLSX

우선 구현 대상.

이유:

- 셀 주소가 명확하다.
- 하이라이트와 적용 UX 검증이 쉽다.
- 업무 가치가 분명하다.

구현:

- parser가 sheet/cell/value/formula 구조를 제공
- LLM은 cell anchor 기반 제안 생성
- apply는 openpyxl로 artifact 생성
- 프론트는 셀 하이라이트와 제안 카드 동기화

지원 change_type:

- amount_check
- formula_error
- date_format
- missing_value
- consistency_check

### HWP

초기 핵심 포맷이지만 적용 난도가 높다.

v0 목표:

- 텍스트/문단 구조 추출
- text_match anchor 생성
- 문단 단위 또는 텍스트 검색 기반 하이라이트
- 수정 전/후 제안 카드
- 적용/거절 상태 관리

v0에서 실제 HWP patch는 필수로 두지 않는다.

후속:

- HWP 라이브러리 기반 실제 수정본 생성
- anchor 정확도 개선
- 문단 ID 또는 control ID 기반 위치 추적

지원 change_type:

- tone
- missing_field
- legal_risk
- date_format
- pii_masking
- form_alignment

### PDF

v0에서는 보조 포맷.

목표:

- 텍스트 기반 분석
- page/text_match 기반 하이라이트
- 실제 원본 patch는 제외

### DOCX/PPTX

이미 일부 렌더링 및 PPTX patch 흔적이 있으므로, 후속으로 통합한다.

DOCX:

- paragraph/run anchor
- page image highlight는 보조

PPTX:

- slide_index + shape_index anchor
- table_cell anchor 유지

## 10. Frontend 설계

### 상태 흐름

`Workspace/index.jsx`는 현재 `previewData`를 중심으로 뷰어에 파일을 전달한다.

v0 확장:

```text
previewData
  snippetData
    editSuggestions
    changeHighlights
```

추가 API:

- 파일 선택 시 `/uploads/{id}/changes/` 호출
- `changeHighlights`와 `DocumentChange` 상태 병합
- 적용/거절 후 로컬 상태 갱신

### 컴포넌트

권장 신규 컴포넌트:

```text
frontend/src/pages/Workspace/ChangeSuggestionPanel.jsx
frontend/src/pages/Workspace/ChangeSuggestionCard.jsx
frontend/src/pages/Workspace/ChangeSummaryBar.jsx
frontend/src/pages/Workspace/AutomationCandidateCard.jsx
```

역할:

- `ChangeSuggestionPanel`: 현재 문서의 변경 제안 목록
- `ChangeSuggestionCard`: 원문/수정안/이유/적용/거절
- `ChangeSummaryBar`: 적용됨/대기/거절 개수 표시
- `AutomationCandidateCard`: 조용한 자동화 후보 표시

### 뷰어 동기화

카드 클릭:

- 해당 highlight로 스크롤
- highlight를 강조

문서 highlight 클릭:

- 해당 suggestion card 선택

적용:

- 카드 status 변경
- highlight status 변경
- 가능하면 문서 프리뷰도 optimistic update

거절:

- 카드 접힘 또는 muted 상태
- highlight 숨김 또는 rejected 스타일

## 11. Workflow Inference v0

처음부터 ML 기반으로 만들지 않는다.

규칙 기반 후보 생성:

```text
같은 사용자
7~30일 기간
비슷한 file_type
비슷한 document_fingerprint 또는 document_type
비슷한 intent 조합
비슷한 reference 사용
3회 이상 반복
적용/다운로드/복사 같은 성공 행동 존재
```

후보 생성 예:

```json
{
  "title": "청약신청서 검토 및 결과 요약",
  "observed_steps": [
    {"type": "input", "label": "청약신청서 업로드"},
    {"type": "reference", "label": "청약 기준표 참조"},
    {"type": "validate", "label": "조건/누락/리스크 검토"},
    {"type": "generate", "label": "검토 요약 작성"}
  ],
  "missing_context_questions": [
    "검토 결과는 보통 누구에게 전달하나요?",
    "최종본은 어디에 저장하나요?"
  ]
}
```

후보 생성 위치:

- Celery periodic task
- 또는 사용자의 작업 완료 후 lightweight sync task

추천:

```text
documents.detect_workflow_candidates
```

를 새 Celery task로 추가한다.

## 12. Candidate to Pipeline

`WorkflowCandidate`를 수락하면 다음 변환을 수행한다.

```text
WorkflowCandidate
-> Pipeline(name, type="A", trigger_meta={source: "candidate"})
-> PipelineStep[]
```

스텝 매핑:

```text
input/reference -> trigger 또는 rag
extract/compare/validate/rewrite/format/generate -> ai_action
output/delivery -> output
```

예:

```text
1. trigger: HWP 청약신청서 업로드
2. rag: 청약 기준표 참조
3. ai_action: 신청자 정보 추출 및 조건 비교
4. ai_action: 누락/리스크 검토
5. output: 검토 결과 요약 생성
```

외부 delivery는 v0에서 질문으로 남긴다.

```text
검토 결과는 보통 어디로 전달하나요?
```

사용자가 답하면 output step config에 저장한다.

## 13. 테스트 전략

### Backend

테스트 대상:

- DocumentChange CRUD/소유권
- apply/reject 상태 전이
- upload별 changes 조회
- change_highlights 변환
- ActivityEvent 기록
- WorkflowCandidate 생성 규칙
- candidate -> Pipeline 변환

주요 보안:

- 다른 사용자의 upload/change/candidate 접근은 404
- LLM이 만든 anchor/apply_payload도 서버에서 검증

### AX Engine

테스트 대상:

- XLSX parser가 cell 구조 반환
- HWP parser가 문단/text anchor 후보 반환
- LLM JSON 검증기
- invalid JSON fallback
- edit_suggestions -> change_highlights 변환
- apply_document_changes XLSX artifact 생성

### Frontend

테스트 대상:

- suggestion card 렌더링
- apply/reject 버튼 동작
- highlight 클릭과 카드 선택 동기화
- file switch 시 changes 재조회
- automation candidate quiet card 표시

## 14. 단계별 구현 순서

### Step 1: 계약 고정

- `edit_suggestion.v1` JSON schema 문서화
- `change_highlights v1` 문서화
- AX Engine mock result 생성

### Step 2: Backend 저장 모델

- `DocumentChange` 모델/API
- apply/reject API
- Chat callback에서 `edit_suggestions` 저장
- `change_highlights` 생성 로직 정리

### Step 3: XLSX end-to-end

- cell anchor suggestion
- 셀 하이라이트
- 적용/거절
- XLSX artifact 생성

### Step 4: HWP viewer suggestion

- HWP text/paragraph anchor
- 제안 카드
- text_match 하이라이트
- 적용 상태 관리

### Step 5: Activity Capture

- 핵심 이벤트 기록
- `UserActionLog` 확장 또는 `ActivityEvent` 추가

### Step 6: WorkflowCandidate v0

- 규칙 기반 후보 생성
- workspace quiet card
- dashboard 후보 목록

### Step 7: Pipeline 연결

- candidate accept
- Pipeline/PipelineStep 생성
- Pipeline detail 화면에서 초안 편집

## 15. 구현 시 주의사항

- HWP v0에서 실제 patch를 필수 목표로 잡지 않는다.
- LLM 출력은 반드시 검증 후 저장한다.
- 프론트는 `snippet_data`만 믿지 말고 서버 상태를 재조회할 수 있어야 한다.
- apply/reject는 서버 상태가 source of truth다.
- 자동화 후보는 사용자 작업 중에 모달로 방해하지 않는다.
- "공문체 변환" 같은 단일 액션을 파이프라인으로 과대해석하지 않는다.
- workflow inference는 내부 개념으로 유지하고, 사용자에게는 짧은 제안으로 번역한다.

## 16. 다음 세부 문서

이 문서 이후 바로 쪼갤 수 있는 구현 문서:

1. `edit-suggestion-json-schema-v1-ko.md`
2. `document-change-api-v0-ko.md`
3. `xlsx-edit-spike-v0-ko.md`
4. `hwp-anchor-strategy-v0-ko.md`
5. `workflow-candidate-rules-v0-ko.md`
