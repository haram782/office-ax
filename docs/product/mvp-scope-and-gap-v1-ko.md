# Office-AX MVP 스코프와 갭 정의 v1

문서 상태: 현재 MVP 전체 범위의 기준 문서. 과금, 토큰/비용 추적, 대시보드, 운영자 도구까지 포함한 제품 범위는 이 문서를 우선한다.

## 1. 문서의 목적

이 문서는 Office-AX의 MVP 범위, 제외 범위, 현재 갭, 과금/사용량 측정 방향을 한 곳에 정리한다.

이전 문서들은 문서 수정 AX의 제품 경험과 patcher 구현 방향을 주로 다뤘다.

이 문서는 조금 더 넓게 본다.

- 어떤 사용자 경험까지 MVP로 닫을 것인가
- 어떤 문서 포맷을 어느 수준까지 지원한다고 말할 것인가
- 지금 껍데기만 있는 대시보드, 토큰 사용량, 과금 모델을 어떻게 MVP 수준으로 다룰 것인가
- 실제 파일 수정 기능과 운영/비용 추적을 어떤 순서로 붙일 것인가

MVP의 목표는 완전한 SaaS가 아니라, 파일 업로드부터 수정본 다운로드와 사용량 확인까지 하나의 납득 가능한 흐름을 만드는 것이다.

## 2. MVP 한 줄 정의

Office-AX MVP는 한국 업무 문서를 업로드하고, AI에게 수정 또는 검토를 요청하면, 검증 가능한 변경 제안과 실제 수정본을 만들고, 사용량과 비용을 최소 수준으로 추적하는 문서 수정 AX다.

핵심 성공 장면:

```text
사용자가 XLSX 파일을 업로드한다.
채팅에 "날짜 형식 맞추고 금액 표시 정리해줘"라고 입력한다.
AI가 변경 제안을 만든다.
사용자는 변경 항목을 확인하고 전체 반영한다.
Office-AX가 수정본 artifact를 생성한다.
사용자는 버전 탭에서 수정본을 다운로드한다.
대시보드에서 이번 달 AI 처리량과 예상 사용량을 확인한다.
```

## 3. MVP 제품 원칙

### 3.1 넓은 자동화보다 좁은 완성도

MVP는 모든 문서를 고치는 제품이 아니다.

우선 XLSX 중심의 문서 수정 경험을 완성한다.

PDF/HWP는 한국 업무 문서 흐름에서 중요하지만, MVP에서는 "검토와 제한적 처리" 수준으로 둔다.

### 3.2 LLM 답변보다 산출물

사용자가 기대하는 가치는 "AI가 이렇게 하면 된다고 말함"이 아니라 "실제 파일이 바뀜"이다.

따라서 MVP 기준에서 가장 중요한 산출물은 다음이다.

- `DocumentChange`
- `DocumentVersion`
- artifact 파일
- 변경 제안 상태
- 실패 이유

### 3.3 과금은 결제보다 측정이 먼저다

지금 단계에서 PG 결제나 구독 플랜을 바로 붙이는 것은 이르다.

MVP에서는 실제 과금보다 다음이 먼저다.

- 어떤 LLM 호출이 발생했는지 기록한다.
- 호출별 입력/출력 토큰 또는 추정 토큰을 기록한다.
- 모델, 공급자, latency, 성공/실패를 기록한다.
- 사용자별 월간 사용량을 보여준다.
- 운영자가 비용이 어디서 발생하는지 볼 수 있게 한다.

실제 결제는 사용량 측정이 안정된 뒤 붙인다.

## 4. 현재 구현 기준선

현재까지 구현된 핵심 흐름:

- Google OAuth 및 게스트 인증
- 문서 업로드
- AX Engine 기반 문서 분석
- 채팅 기반 Q&A
- 채팅 의도 판별
- `PatchPlan` 생성
- `DocumentChange` 저장
- 변경 항목 적용/거절
- patcher 실행
- `DocumentVersion` artifact 저장
- 버전 목록과 다운로드
- XLSX `replace_cell`
- XLSX `set_cell_style`
- XLSX `set_number_format`
- XLSX `set_formula`
- PDF annotate/redact overlay 계열
- HWP worker 기반 제한적 텍스트 치환
- 대시보드 통계 껍데기
- `UserActionLog` 기반 행동 로그 일부

현재 껍데기 또는 미완성 영역:

- 대시보드 토큰/잔액 수치가 실제 사용량과 연결되어 있지 않다.
- LLM 호출별 사용량 기록 모델이 없다.
- 로컬 Gemini CLI 사용 시 실제 토큰 수를 알 수 없거나 일관되게 수집되지 않는다.
- 운영자용 사용량 조회 도구가 없다.
- 과금 정책이 제품 문구와 데이터 모델로 정리되지 않았다.
- 채팅 기반 PatchPlan 생성 후 프론트 갱신이 실사용 기준으로 충분히 매끄러운지 검증이 더 필요하다.
- 실패한 변경 항목을 사용자가 어떻게 이해하고 재요청할지 UX가 약하다.

## 5. MVP 포함 범위

### 5.1 인증과 사용자

포함:

- Google OAuth 로그인
- 게스트/테스트 계정
- 사용자별 문서, 채팅, 버전, 사용량 분리

제외:

- 조직/팀 계정
- 권한 그룹
- SSO
- 감사 로그 정식 제품화

### 5.2 문서 업로드와 뷰어

포함:

- XLSX 업로드와 미리보기
- PDF 업로드와 미리보기
- HWP 업로드와 제한적 미리보기 또는 분석 결과 표시
- 파일별 채팅 맥락 연결
- 수정본 버전 탭
- artifact 다운로드

제외:

- 브라우저 직접 편집기
- Word/PowerPoint 수준의 정식 WYSIWYG 뷰어
- 복잡한 레이아웃 보존 편집

### 5.3 문서 수정

MVP에서 "정식 수정 지원"이라고 부를 수 있는 범위:

- XLSX 셀 값 변경
- XLSX 셀 서식 변경
- XLSX 표시 형식 변경
- XLSX 단일 셀 수식 설정

MVP에서 "제한적 지원"이라고 표현할 범위:

- PDF 주석 또는 redact overlay
- HWP 텍스트 치환
- DOCX/PPTX 텍스트 또는 미리보기 기반 검토

MVP에서 제외:

- XLSX 행/열 삽입
- XLSX 병합/테이블 구조 변경
- HWP 표/양식 수정
- PDF 구조 수정
- DOCX/PPTX 양식 수정
- 전체 문서 재생성

### 5.4 채팅 기반 수정 요청

포함:

- 파일이 선택된 상태에서 채팅 입력 시 Q&A와 수정 의도 구분
- 수정 의도면 PatchPlan 생성
- 우측 변경 패널에 변경 항목 표시
- 채팅 말풍선에 수정 계획 상태 표시
- 전체 반영
- 보류 또는 재요청

MVP에서 필요한 최소 상태:

- 생성 중
- 변경 제안 준비
- 생성 실패
- 수정본 생성 중
- 수정본 준비

제외:

- 실시간 스트리밍 상태 표시
- 멀티턴 PatchPlan diff 병합
- 협업 댓글

### 5.5 대시보드

포함:

- 이번 달 처리 문서 수
- 이번 달 생성된 수정본 수
- 실패한 작업 수
- AI 호출 수
- 추정 토큰 사용량
- 추정 비용
- 남은 크레딧 또는 월 한도

제외:

- 회계 수준의 청구서
- 카드 결제
- 세금계산서
- 팀별 비용 배분

## 6. 과금 모델 MVP

### 6.1 지금 당장 결제하지 않는다

MVP에서는 실제 결제를 붙이지 않는다.

대신 내부 크레딧 모델로 시작한다.

```text
월 무료 크레딧
문서 분석 1회 = n credit
PatchPlan 생성 1회 = n credit
수정본 생성 1회 = n credit
```

이 방식의 장점:

- 실제 LLM 비용과 사용자 가치 사이의 비율을 관찰할 수 있다.
- 요금제를 나중에 바꿔도 데이터가 남는다.
- 결제 시스템 없이도 사용량 제한과 운영 판단이 가능하다.

### 6.2 초기 플랜 가설

초기 문구 수준의 플랜:

```text
Free Trial
- 월 20회 AI 문서 처리
- 파일당 크기 제한
- XLSX 수정본 생성 가능

Starter
- 월 300회 AI 문서 처리
- 사용량 대시보드
- XLSX/PDF/HWP 기본 처리

Business
- 월 2,000회 이상
- 조직 계정
- 관리 대시보드
- 보관 정책
```

MVP 구현에서는 Free Trial과 Starter의 경계만 필요하다.

Business는 문구와 데이터 구조만 염두에 둔다.

### 6.3 과금 단위

MVP에서 과금 또는 사용량 집계 단위는 token 하나만으로 두지 않는다.

사용자에게 token은 직관적이지 않다.

따라서 내부 집계와 사용자 표시를 분리한다.

내부 집계:

- input tokens
- output tokens
- model
- provider
- estimated cost
- latency
- task type

사용자 표시:

- AI 처리 n회
- 문서 수정본 생성 n회
- 이번 달 사용량 n%
- 남은 크레딧 n

## 7. 사용량 측정 설계

### 7.1 UsageEvent 모델 후보

기존 `UserActionLog`는 행동 이벤트 로그에 가깝다.

LLM 비용과 사용량 측정은 별도 모델로 분리하는 것이 좋다.

후보 모델:

```text
UsageEvent
  user
  session
  upload_log
  chat_message
  document_version
  event_type
  provider
  model
  input_tokens
  output_tokens
  estimated_input_tokens
  estimated_output_tokens
  token_source
  estimated_cost_usd
  estimated_cost_krw
  latency_ms
  status
  error_code
  meta
  created_at
```

`event_type` 후보:

- document_analysis
- chat_qa
- intent_classification
- patch_plan_generation
- patch_render
- artifact_download

`token_source` 후보:

- provider_reported
- estimated
- unavailable

### 7.2 로컬 Gemini CLI의 토큰 문제

현재 로컬 Gemini CLI 경로는 API 응답처럼 토큰 사용량이 안정적으로 내려오지 않을 수 있다.

MVP에서는 다음처럼 처리한다.

- 실제 토큰이 있으면 provider_reported로 저장한다.
- 없으면 문자 수 기반 추정치를 저장한다.
- 추정치임을 명확히 표시한다.

초기 추정 규칙:

```text
estimated_input_tokens = ceil(input_chars / 3)
estimated_output_tokens = ceil(output_chars / 3)
```

한국어 기준으로 정확하지는 않지만, MVP 운영용 추세 파악에는 충분하다.

향후 API 전환 시 provider_reported 토큰으로 교체한다.

### 7.3 비용 계산

MVP에서는 실제 청구가 아니라 예상 비용 추적이 목적이다.

따라서 모델별 단가 테이블을 코드나 설정에 둔다.

```text
LLMPricing
  provider
  model
  input_per_1m_tokens_usd
  output_per_1m_tokens_usd
  effective_from
```

처음에는 DB 모델이 아니라 설정 상수로 시작해도 된다.

단, 비용 계산 결과는 `UsageEvent`에 스냅샷으로 저장해야 한다.

이유:

- 나중에 단가가 바뀌어도 과거 비용 추정값이 흔들리지 않는다.
- 운영자가 특정 날짜 기준 비용을 다시 볼 수 있다.

## 8. 운영자 조회 도구

MVP에서 필요한 운영자 도구는 복잡한 admin dashboard가 아니다.

최소 요구:

- 사용자별 월간 사용량 조회
- LLM 호출 실패 목록 조회
- 비용 상위 사용자 조회
- 비용 상위 작업 유형 조회
- 특정 문서의 LLM 호출 이력 조회

구현 후보:

1. Django admin에 `UsageEvent` 등록
2. `/api/v1/admin/usage/summary/` 내부 API
3. CSV export

우선순위:

```text
Django admin 등록
→ 월간 summary API
→ CSV export
```

MVP에서는 Django admin만으로도 충분할 수 있다.

## 9. 대시보드 갭

현재 대시보드는 토큰과 잔액 형태의 UI를 이미 일부 갖고 있다.

하지만 실제 데이터 연결이 부족하다.

MVP 갭:

- `token_used`가 실제 UsageEvent 합계가 아니다.
- `token_total`이 사용자 플랜 또는 월 한도와 연결되어 있지 않다.
- `balance`, `deposit`의 의미가 불명확하다.
- 문서 처리 수와 수정본 생성 수가 구분되지 않는다.
- 예상 소진일 계산 기준이 없다.

MVP 수정 방향:

- `tokens.used` → 이번 달 estimated total tokens
- `tokens.total` → 현재 플랜 월 token allowance 또는 credit allowance
- `balance` → 남은 credit
- `deposit` → MVP에서는 숨기거나 "충전금" 대신 "이번 달 한도"로 표현
- `processed` → 문서 분석 수와 수정본 생성 수를 분리

## 10. MVP 갭 목록

### 10.1 제품 경험 갭

- 채팅 PatchPlan 생성이 완료됐을 때 프론트가 안정적으로 갱신되는지 확인 필요
- 생성 중 말풍선과 완료 말풍선의 관계 정리 필요
- 전체 반영이 apply-all과 patch trigger까지 자연스럽게 이어지는지 확인 필요
- 실패한 change를 사용자가 이해할 수 있는 문구가 부족하다
- 샘플 문서 기반 데모 시나리오가 없다

### 10.2 문서 수정 갭

- XLSX는 MVP 핵심 범위까지 거의 들어왔지만, 실제 샘플 파일 E2E 검증이 필요하다
- PDF는 한글 redact overlay 회귀가 계속 유지되는지 확인해야 한다
- HWP는 "정식 지원"이 아니라 제한적 텍스트 처리로 표현해야 한다
- DOCX/PPTX는 MVP 핵심 수정 범위에서 제외해야 한다

### 10.3 사용량/비용 갭

- LLM 호출별 UsageEvent가 없다
- provider/model/latency/status 기록이 없다
- 로컬 CLI 호출의 추정 토큰 계산이 없다
- dashboard stats가 실제 사용량과 연결되어 있지 않다
- admin 조회 도구가 없다

### 10.4 운영 갭

- 실패한 Celery task 관찰 도구가 부족하다
- artifact 저장량 추적이 부족하다
- 오래된 파일 보관 정책은 일부 있어도 사용자에게 노출되지 않는다
- 플랜별 제한 정책이 없다

## 11. MVP 구현 우선순위

### Phase 0. 현재 브랜치/PR 정리

먼저 현재 머지 충돌이나 detached HEAD 상태를 정리한다.

기획과 구현 diff가 섞이면 안 된다.

### Phase 1. MVP happy path 고정

목표:

XLSX 하나로 업로드부터 수정본 다운로드까지 매끄러운 데모를 만든다.

작업:

- 샘플 XLSX 파일 선정
- 채팅 수정 요청 시나리오 3개 작성
- PatchPlan 생성 완료 후 프론트 갱신 확인
- 전체 반영 → patch trigger → artifact 다운로드 흐름 확인
- 실패 없는 happy path E2E 테스트 정리

### Phase 2. 사용량 측정 MVP

목표:

실제 과금 전 비용을 볼 수 있게 한다.

작업:

- `UsageEvent` 모델 추가
- AX Engine LLM 호출 지점에서 usage payload 생성
- backend callback에서 UsageEvent 저장
- token 추정 로직 추가
- task type별 사용량 기록

### Phase 3. 대시보드 실제 데이터 연결

목표:

더미 토큰/잔액 UI를 실제 월간 사용량으로 교체한다.

작업:

- dashboard stats API가 UsageEvent 집계 사용
- 월간 token/credit 사용량 계산
- 문서 처리 수와 수정본 생성 수 분리
- 비용 추정값 표시

### Phase 4. 운영자 조회 도구

목표:

개발자가 비용과 실패를 볼 수 있게 한다.

작업:

- Django admin에 UsageEvent 등록
- 사용자별 월간 usage 필터
- 실패 이벤트 필터
- 비용 상위 이벤트 조회

### Phase 5. MVP 메시지 정리

목표:

지원 범위와 제한을 제품 문구로 명확히 한다.

작업:

- XLSX 정식 수정 지원
- PDF/HWP 제한적 지원
- DOCX/PPTX 실험 또는 preview 중심
- 결제는 아직 trial/credit 기반

## 12. MVP 완료 기준

MVP는 다음이 가능하면 완료로 본다.

- 신규 사용자가 로그인한다.
- XLSX 파일을 업로드한다.
- 채팅으로 수정 요청을 한다.
- AI 변경 제안이 생성된다.
- 사용자가 전체 반영한다.
- 수정본 artifact가 생성된다.
- 버전 탭에서 수정본을 다운로드한다.
- 대시보드에서 이번 달 AI 사용량과 예상 비용을 확인한다.
- 운영자는 사용자의 LLM 호출 이력을 조회할 수 있다.
- 실패한 작업은 최소한 원인과 재시도 가능 여부를 알 수 있다.

## 13. MVP에서 의도적으로 하지 않을 것

- 실결제
- 조직 관리
- 권한 그룹
- 이메일 수신 자동화 정식 출시
- 반복 파이프라인 실행 엔진
- HWP 표/양식 수정
- PDF 구조 수정
- DOCX/PPTX 정식 수정 지원
- 템플릿 기반 전체 문서 재생성
- 멀티문서 RAG 기반 자동 작성

이것들은 중요하지 않아서 제외하는 것이 아니다.

MVP에서 핵심 가치를 흐리거나 구현 리스크를 과도하게 키우기 때문에 뒤로 미룬다.

## 14. 다음 기획 문서 후보

이 문서 이후 필요한 세부 문서:

1. `usage-metering-design-v1-ko.md`
   - UsageEvent 모델
   - token 추정
   - 비용 계산
   - dashboard aggregation

2. `mvp-demo-scenarios-v1-ko.md`
   - 샘플 문서
   - 사용자 요청
   - 기대 PatchPlan
   - 기대 artifact 결과

3. `billing-credit-policy-v1-ko.md`
   - 무료 크레딧
   - 월 한도
   - 사용자 표시 문구
   - 실제 결제 전환 기준

## 15. 한 줄 요약

Office-AX MVP의 다음 목표는 더 많은 문서 포맷을 얕게 넓히는 것이 아니라, XLSX 중심의 실제 수정본 생성 경험과 LLM 사용량/비용 추적을 연결해 "써볼 수 있는 문서 수정 SaaS"의 최소 단위를 닫는 것이다.
