# Office-AX Product Docs

이 디렉터리는 Office-AX 제품 기획, 문서 수정 AX 설계, PatchPlan 계약, MVP 범위 문서를 보관한다.

새 작업을 시작할 때는 이 파일을 먼저 보고, 목적에 맞는 문서만 이어서 읽는다.

## 1. 디렉토리 구조

```text
docs/product/
  README.md
  strategy/       제품 방향, MVP 범위, 장기 포지셔닝
  roadmap/        구현 순서와 작업 묶음
  architecture/   시스템 설계, 라이브러리/스택 판단
  contracts/      LLM, 백엔드, patcher, 프론트가 공유하는 계약
  feature-specs/  특정 기능 단위 상세 기획
```

문서를 찾을 때는 다음 순서로 본다.

```text
왜 하는가       → strategy/
무엇부터 하는가 → roadmap/
어떻게 구성할까 → architecture/
무엇을 주고받나 → contracts/
기능별 세부사항 → feature-specs/
```

## 2. 현재 기준 문서

### 클로즈드 베타 런칭 계획

- `strategy/closed-beta-launch-plan-v1-ko.md`

MVP 마감과 첫 외부 공개(클로즈드 베타)의 기준 문서다. 현재 작업 묶음은 이 문서를 우선한다.

다음 내용을 확인할 때 우선 읽는다.

- 베타 공개 범위와 대상 (공공·행정 인접 직군 지인 5~20명)
- 배포/인증/터널 구성 (로컬 맥 + 고정 호스트네임 터널 + OAuth allowlist)
- 크레딧 하드 한도와 민감정보 고지 정책
- 구현 순서 (M1~M5)와 운영 체크리스트
- 베타 성공 기준 (정성 인터뷰)과 인터뷰 질문지

### MVP 전체 범위

- `strategy/mvp-scope-and-gap-v1-ko.md`

Office-AX MVP의 현재 기준 문서다.

다음 내용을 확인할 때 우선 읽는다.

- MVP 포함/제외 범위
- 문서 포맷별 지원 수준
- 과금 모델 초안
- 토큰/비용/사용량 측정 방향
- 대시보드 갭
- 운영자 조회 도구
- 구현 우선순위

### 문서 수정 로드맵

- `roadmap/document-editing-ax-next-roadmap-v1-ko.md`

문서 수정 AX의 다음 구현 순서를 다룬다.

다음 내용을 확인할 때 읽는다.

- XLSX 중심 구현 순서
- `set_number_format`, `set_formula` 이후 확장
- PDF/HWP/DOCX/PPTX 진입 순서
- 테스트 전략
- 문서 수정 기능의 다음 묶음

### PatchPlan 계약

- `contracts/patch-plan-schema-v0-ko.md`

LLM, 백엔드, patcher, 프론트가 공유하는 구조화된 변경 계약이다.

새 operation을 추가하거나 `DocumentChange` 저장 구조를 바꿀 때 반드시 함께 갱신한다.

### 문서 수정/생성 실행 레이어 설계

- `architecture/document-edit-execution-layer-design-v1-ko.md`

LLM-백엔드 책임 분리, 작업 복잡도 계층(T0~T3), TargetResolver 일반화(wire contract), Patch Contract 확장 방향, render validation, 베타 전 최소 범위를 다룬다.

다음 내용을 확인할 때 읽는다.

- AnchorResolver를 DOCX/HWP로 확장하는 방식
- T2(표/필드 수정) anchor variant와 candidate_source 설계
- confidence 이원화 (semantic vs resolution)
- PDF 구조적 invariant 검증 목록
- 이미지/PII 정책 미결 옵션

### 스택/라이브러리 판단

- `architecture/stack-library-audit-v1-ko.md`

현재 사용하는 라이브러리와 대체/보강 후보를 정리한 아키텍처 판단 문서다.

PDF, HWP, LLM gateway, Office 고충실도 뷰어처럼 교체 비용이 큰 결정을 하기 전에 읽는다.

## 3. 배경 및 세부 설계 문서

### 문서 양식 수정 AX v1

- `feature-specs/document-format-editing-ax-v1-ko.md`

XLSX `set_cell_style` 중심으로 "텍스트 치환을 넘어 양식 수정이 가능하다"는 제품/기술 가설을 정리한 문서다.

현재는 v1 POC 배경 문서로 본다.

### 문서 수정 및 업무 흐름 추론 구현 설계 v0

- `architecture/document-workflow-implementation-design-v0-ko.md`

초기 구현 설계 문서다.

`DocumentChange`, activity capture, workflow inference, pipeline draft 같은 장기 구조를 볼 때 참고한다.

현재 구현과 일부 이름이나 우선순위가 다를 수 있으므로, 최신 스코프는 `strategy/mvp-scope-and-gap-v1-ko.md`, 최신 PatchPlan 계약은 `contracts/patch-plan-schema-v0-ko.md`를 우선한다.

### 뷰어 중심 문서 업무 자동화 v0

- `strategy/viewer-first-workflow-automation-v0-ko.md`
- `strategy/viewer-first-workflow-automation-v0.md`

초기 제품 방향과 장기 자동화 가설을 정리한 문서다.

한국어 문서를 기준으로 보고, 영어 문서는 보존용 mirror로 둔다.

현재 MVP 구현 범위는 `strategy/mvp-scope-and-gap-v1-ko.md`를 우선한다.

## 4. 현재 MVP 구현 흐름

현재 MVP는 다음 흐름을 닫는 것을 목표로 한다.

```text
파일 업로드
  → 문서 분석
  → 채팅에서 Q&A 또는 수정 의도 판별
  → PatchPlan 생성
  → DocumentChange 저장
  → 변경 제안 표시
  → 적용/거절
  → patcher 실행
  → DocumentVersion artifact 저장
  → 버전 탭에서 다운로드
  → UsageEvent 기록
  → 대시보드 사용량/비용 집계
```

MVP에서 가장 중요한 포맷은 XLSX다.

PDF/HWP는 한국 업무 문서에서 중요하지만, MVP에서는 제한적 지원 또는 검토 중심으로 둔다.

DOCX/PPTX는 정식 수정 지원보다 미리보기/검토/후속 확장 대상으로 본다.

## 5. 문서 갱신 규칙

새 기획을 추가할 때:

- 제품 전체 범위가 바뀌면 `strategy/mvp-scope-and-gap-v1-ko.md`를 갱신한다.
- PatchPlan operation이나 anchor가 바뀌면 `contracts/patch-plan-schema-v0-ko.md`를 갱신한다.
- 구현 순서나 작업 묶음이 바뀌면 `roadmap/document-editing-ax-next-roadmap-v1-ko.md`를 갱신한다.
- 라이브러리, 런타임, 외부 도구 판단이 바뀌면 `architecture/stack-library-audit-v1-ko.md`를 갱신한다.
- 장기 자동화나 workflow inference 아이디어는 v0 문서를 직접 고치기보다 새 문서로 분리한다.

중복 문서를 만들지 않는다.

이미 있는 문서가 배경 문서가 되었으면 삭제하기보다 상단 상태를 갱신한다.

## 6. 다음 세부 문서 후보

아직 별도 문서로 쪼개지 않은 후보:

- `mvp-demo-scenarios-v1-ko.md` — 샘플 문서와 기대 결과. 베타 계획 M4의 산출물과 겹치므로 필요 시 분리
- `billing-credit-policy-v1-ko.md` — 실결제 전환 기준. 베타 크레딧 초기값은 `closed-beta-launch-plan-v1-ko.md` 6절이 커버하며, 베타 인터뷰 결과를 입력으로 작성한다

`usage-metering-design-v1-ko.md`는 UsageEvent 구현 완료(대시보드 집계 연결 포함)로 후보에서 제외했다.
