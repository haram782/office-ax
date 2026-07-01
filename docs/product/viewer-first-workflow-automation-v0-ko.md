# Office-AX 뷰어 중심 문서 업무 자동화 v0

문서 상태: 초기 제품 방향과 장기 자동화 가설 문서. 현재 MVP 구현 범위는 `mvp-scope-and-gap-v1-ko.md`를 우선한다.

## 1. 제품 방향

Office-AX는 처음에는 AI 문서 수정 워크스페이스처럼 보이지만, 더 깊은 목표는 사용자의 반복되는 문서 업무 흐름을 추론하고 자동화로 전환하는 것이다.

첫 사용자 가치가 "파이프라인을 만드세요"가 되어서는 안 된다. 첫 가치는 다음 흐름이어야 한다.

- 문서를 업로드한다.
- 뷰어에서 문서를 확인한다.
- AI에게 검토나 수정을 요청한다.
- 문서 위에서 수정 제안을 확인한다.
- 적용, 거절, 다운로드를 한다.

장기 가치는 다음이다.

- 사용자의 문서 작업을 관찰한다.
- 입력 문서, 참조 문서, 작업 단계, 산출물, 전달 방식의 반복 흐름을 추론한다.
- 미래 작업을 줄일 수 있을 때만 자동화를 제안한다.
- 고급 사용자는 추론된 흐름을 파이프라인 편집기에서 다듬을 수 있다.

## 2. 포지셔닝

Office-AX는 사용자가 GPT, Gemini, Claude에 문서를 업로드하거나 붙여넣고, 답변을 다시 파일에 복사하는 흐름을 대체해야 한다.

일반 LLM 웹 채팅보다 더 만족스러워야 하는 이유는 문서, AI 응답, 수정 제안, 최종 산출물이 하나의 작업공간 안에 있기 때문이다.

제품 문장:

> AI 문서 작업은 문서 옆이 아니라 문서 위에서 일어나야 한다.

사용자-facing 문장:

> GPT로 복붙하던 문서 수정, 이제 문서 위에서 확인하고 적용하세요.

## 3. 핵심 제품 가설

Office-AX는 사용자에게 처음부터 자동화를 설계하라고 요구하지 않는다.

사용자는 평소처럼 일한다.

1. 문서를 업로드한다.
2. 검토, 수정, 형식 정리, 비교, 생성을 요청한다.
3. 유용한 제안을 적용하거나 거절한다.
4. 결과물을 다운로드하거나 재사용한다.

Office-AX는 이 행동을 조용히 학습한다.

자동화 전환 순서:

1. C: 반복되는 문서 업무 흐름을 추론한다.
2. B: 추론된 흐름을 재사용 가능한 규칙으로 저장할지 제안한다.
3. A: 저장된 규칙을 고급 설정 가능한 파이프라인으로 편집하게 한다.

즉 파이프라인 편집기는 첫 진입점이 아니다. 파이프라인 편집기는 추론된 업무 흐름을 명시적으로 확인하고 조정하는 장소다.

## 4. 첫 감탄 순간

첫 감탄은 뷰어 안에서 문서가 실제로 수정되는 듯한 경험이어야 한다.

- AI가 문서의 관련 위치를 찾는다.
- 해당 위치가 하이라이트된다.
- 사용자는 원문과 수정안을 비교한다.
- 사용자는 제안을 적용하거나 거절한다.
- 최종 문서가 단순 설명이 아니라 실제 결과물처럼 느껴진다.

첫 감탄은 감성적이고 시각적이어야 한다. 문서가 AI와 함께 직접 작업되고 있다는 느낌이 중요하다.

더 깊은 리텐션은 이후에 생긴다. Office-AX가 반복되는 흐름을 알아차리고 자동화를 제안하는 순간이다.

## 5. 초기 문서 포맷 전략

HWP와 XLSX를 우선한다.

### HWP

HWP는 한국 업무 문서 시장에서 중요하다.

초기 범위:

- 문서 텍스트와 구조 추출
- 문단 또는 텍스트 anchor 식별
- 검토 및 수정 제안 생성
- 대략적인 텍스트 또는 문단 위치 하이라이트
- 공문체, 누락 필드, 리스크 검토, 양식 정렬 같은 업무 문서 작업 지원

후속 범위:

- 정밀한 HWP patch
- 레이아웃 인식 anchor
- 템플릿 기반 문서 생성

### XLSX

XLSX는 정확한 문서 단위 AI 작업을 증명하기 좋다.

초기 범위:

- 셀 단위 구조 추출
- 셀 주소 기반 하이라이트
- 수식, 금액, 날짜, 누락값, 일관성 검토
- 수정값 제안

XLSX는 위치와 적용 UX를 빠르게 검증하기 좋은 초기 spike 포맷이다. 셀 주소가 명확하기 때문이다.

## 6. AI 기능 범위

Office-AX는 사용자가 일반 LLM 도구에서 이미 많이 하는 작업을 지원해야 한다.

- 요약
- 오탈자 수정
- 문장 다듬기
- 공문체 또는 업무 문체 변환
- 문서 리스크 검토
- 누락 항목 탐지
- 모순 발견
- 개인정보 마스킹
- 회사 양식에 맞추기
- 회신, 보고서, 공지, 공문 초안 작성

차별점은 기능이 존재한다는 것 자체가 아니다. 차별점은 Office-AX가 이 작업을 문서-native 경험으로 바꾼다는 점이다.

- 위치 기반 수정 제안
- 수정 전/후 비교
- 적용/거절 컨트롤
- 저장된 규칙
- 추론된 업무 흐름

## 7. 업무 흐름 추론 모델

Office-AX는 반복 프롬프트가 아니라 문서 업무 흐름을 추론해야 한다.

목표 패턴:

```text
Input -> Reference -> Operation -> Output -> Delivery
```

예시:

```text
청약신청서.hwp
-> 청약 자격 기준표.xlsx
-> 신청자 정보 추출, 조건 비교, 누락/리스크 검토
-> 검토 결과 요약서
-> 담당자에게 전달
```

```text
견적서.xlsx
-> 회사 가격 정책표.xlsx
-> 금액/수식/날짜 오류 검토
-> 수정 제안 또는 정정본
-> 최종 파일 다운로드
```

자동화 대상은 문서 업무 흐름이다. "공문체로 바꿔줘" 같은 단일 요청은 workflow 안의 operation이지, 그 자체가 완전한 파이프라인은 아니다.

## 8. 제품 레이어

### 1. Viewer Workspace

사용자가 실제로 일하는 기본 작업공간.

역할:

- 문서 업로드 및 열기
- 문서 미리보기
- AI 채팅
- 수정 제안과 하이라이트 표시
- 적용, 거절, 다운로드 지원

### 2. Activity Capture

백그라운드 이벤트 수집 레이어.

역할:

- 작업을 방해하지 않고 사용자 행동 수집
- 문서 역할, 프롬프트, 참조 문서, 산출물, 적용된 변경 기록
- 이후 업무 흐름 추론에 필요한 근거 보존

### 3. Workflow Inference

지능형 추론 레이어.

역할:

- 이벤트를 업무 단위로 묶기
- 반복되는 문서 업무 패턴 탐지
- 입력, 참조, 작업, 산출물, 전달 단계를 추론
- 제안할 가치가 있는지 점수화

### 4. Automation Suggestion

사용자에게 보이는 자동화 연결 레이어.

역할:

- 작업을 줄일 수 있을 때만 자동화 제안
- 내부 추론 디테일 노출 방지
- 사용자가 저장, 무시, 수정할 수 있게 함

### 5. Pipeline Editor

고급 편집기.

역할:

- 자동화 후보를 파이프라인 초안으로 전환
- 누락 단계, 트리거, 참조 문서, 산출물, 전달 방식을 사용자가 편집
- 향후 이메일, 스케줄, RAG, 외부 전달 채널 연결

### 6. Execution Engine

향후 자동화 실행 런타임.

역할:

- 확정된 파이프라인 실행
- 실행 이력 추적
- 실패, 재시도, 알림 처리

## 9. UX 원칙: 추론을 과하게 설명하지 않는다

사용자는 Office-AX에 일을 하러 온다. 시스템의 추론 과정을 보러 온 것이 아니다.

Office-AX는 백그라운드에서 추론하고, 유용할 때만 말해야 한다.

보여주면 안 되는 것:

- "Input -> Reference -> Operation -> Output -> Delivery"
- "confidence: 0.78"
- "intent: compare"
- "document_role: reference"

보여줘야 하는 것:

- "이 검토 방식, 다음에도 자동으로 적용할까요?"
- "비슷한 문서가 올라오면 먼저 확인해둘게요."
- "이 작업을 저장하면 다음부터 검토 시간을 줄일 수 있어요."

원칙:

> Office-AX는 사용자의 업무 흐름을 설명하지 않는다. 조용히 이해하고, 다음 일을 줄이는 선택지만 제안한다.

## 10. 자동화 제안 노출 위치

세 가지 표면을 사용한다.

### Workspace Quiet Card

작고 방해하지 않는 카드.

예시:

```text
자동화 후보 2개 발견
- 청약신청서 검토
- 견적서 오류 확인
```

### Dashboard Analysis

조금 더 분석적인 화면.

예시:

```text
이번 주 반복 업무
1. 청약신청서 검토 - 5회 반복
2. 견적서 금액 오류 확인 - 4회 반복
```

### Chat Suggestion

자연스럽고 짧은 채팅 제안.

예시:

```text
이 방식은 다음 청약서에도 그대로 쓸 수 있어요.
저장해둘까요?
```

문서 편집 중에는 작업을 막는 모달을 띄우지 않는다.

## 11. 최소 이벤트 어휘

MVP에서 기록할 이벤트:

- document_uploaded
- document_opened
- reference_selected
- prompt_submitted
- llm_response_generated
- edit_suggestion_generated
- edit_suggestion_applied
- edit_suggestion_rejected
- output_generated
- file_downloaded
- message_copied
- automation_suggestion_shown
- automation_suggestion_accepted
- automation_suggestion_dismissed

공통 필드:

- user
- session
- document_id
- file_type
- document_fingerprint
- event_type
- timestamp
- payload

중요 payload 개념:

- document_role: input, reference, output
- intent: extract, compare, validate, rewrite, format, generate, send
- change_types: date_format, pii_masking, missing_field, tone, amount_check, legal_risk
- artifact: source_doc, reference_doc, generated_doc, final_download

## 12. 초기 데이터 개념

아래는 최종 구현 이름이 아니라 기획용 개념이다.

### DocumentObject

작업에 사용된 문서.

역할:

- input
- reference
- output

### TaskRun

하나의 의미 있는 문서 업무 단위.

예시:

- HWP 신청서 하나 검토
- 스프레드시트를 정책표와 비교
- 업로드 자료로 보고서 생성

### TaskStep

업무 안에서 추론된 단계.

유형:

- extract
- compare
- validate
- rewrite
- format
- generate
- send

### WorkflowCandidate

추론된 반복 업무 흐름 후보.

고려 필드:

- title
- user
- observed_steps
- evidence_events
- repeated_count
- confidence
- missing_context_questions
- status: suggested, accepted, dismissed, converted_to_pipeline

### PipelineDraft

사용자가 확인했거나 편집 가능한 workflow candidate 버전.

이후 정식 Pipeline이 될 수 있다.

## 13. 추적되지 않은 외부 컨텍스트

일부 단계는 현재 workspace 밖에서 발생한다.

- 이메일로 파일 받기
- 결과물을 다른 사람에게 전달
- 공유 폴더에 업로드
- ERP 또는 그룹웨어에 입력
- 결재 요청

이 단계를 시스템이 이미 알고 있다고 가정하면 안 된다.

workflow candidate를 보여줄 때 가볍게 보완 질문을 한다.

```text
검토 결과는 보통 어디로 전달하나요?
[다운로드만] [이메일로 발송] [담당자에게 전달] [공유폴더 저장] [직접 입력]
```

이 질문은 문서 편집 중이 아니라 자동화 후보를 다듬는 시점에만 보여준다.

## 14. MVP 권장 순서

다음 순서로 만든다.

### Phase 1: Edit Suggestion Schema

뷰어가 렌더링할 수 있는 구조화된 LLM 출력 포맷을 정의한다.

필수 필드:

- summary
- detected issues
- edit suggestions
- target text 또는 cell address
- replacement
- reason
- confidence
- change type
- anchor hint

### Phase 2: XLSX Spike

정확한 위치 표시와 적용 UX를 검증한다.

범위:

- 셀 단위 문제 탐지
- 셀 하이라이트
- 수정값 제안
- 적용/거절

### Phase 3: HWP Workspace

한국 업무 문서 수정 가치를 검증한다.

범위:

- 문단 또는 text-anchor 하이라이트
- 검토 제안
- 공문체 및 양식 정렬
- 리스크 및 누락 필드 탐지

### Phase 4: Activity Capture

workspace에서 업무 단위 이벤트를 기록하기 시작한다.

범위:

- 업로드
- 프롬프트
- 참조 선택
- 생성된 제안
- 적용/거절된 제안
- 다운로드

### Phase 5: Workflow Candidate v0

복잡한 ML보다 단순 규칙을 먼저 사용한다.

예시 규칙:

```text
7일 안에,
같은 사용자,
비슷한 문서 유형,
비슷한 참조 사용,
비슷한 operation 유형,
3회 이상의 task run,
의미 있는 적용/다운로드 행동
=> workflow candidate 생성
```

### Phase 6: Pipeline Draft

수락된 candidate를 편집 가능한 pipeline draft로 전환한다.

파이프라인 편집기는 빈 캔버스에서 시작하지 않고, 추론된 단계들을 받아야 한다.

## 15. 열린 질문

1. 첫 데모 문서는 무엇인가?
   - HWP 신청서
   - XLSX 견적서 또는 정산서
   - 다른 한국 업무 문서

2. HWP 구현 기준이 되는 오픈소스 라이브러리는 무엇인가?

3. HWP patch는 v0에서 어디까지 가능한가?
   - 텍스트 추출만
   - 대략적 하이라이트
   - 수정본 생성
   - 실제 원본 내 patch

4. 무엇을 성공한 작업으로 볼 것인가?
   - 제안 적용
   - 파일 다운로드
   - 메시지 복사
   - 사용자의 후속 승인

5. RAG 또는 참조 선택은 어떤 의미로 표현할 것인가?
   - 스타일 참조
   - 정책/기준 문서
   - 출력 템플릿
   - 이전 예시

6. 자동화 후보는 언제 보여줄 것인가?
   - 다운로드 이후
   - 반복 프롬프트 이후
   - 대시보드에서만
   - workspace quiet card로

## 16. 다음 기획 문서

권장 후속 문서:

1. `document-edit-suggestion-schema-v0.md`
2. `document-workflow-inference-v0.md`
3. `hwp-xlsx-viewer-mvp-v0.md`
4. `automation-candidate-to-pipeline-v0.md`
