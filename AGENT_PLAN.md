# AGENT_PLAN.md

> 상태: **FINAL / 구현 인계 준비 완료**
>
> 기준 커밋: `main` = `63f5f89615e044fd0e3076ad92119e70d7a5c57d` (PR #32)
>
> 확정일: 2026-07-13
>
> 사용자 결정: `DocumentChange`와 `DocumentVersion`의 additive `failure_code` migration 및 이 vertical slice에 기술적으로 필요한 구현 변경을 허용한다. 구현 세부 선택은 엔지니어링 판단에 위임한다.

## 조사 범위와 판정 기준

- 기준 문서:
  - `docs/product/strategy/closed-beta-launch-plan-v1-ko.md`
  - `docs/product/architecture/document-edit-execution-layer-design-v1-ko.md`
  - `docs/product/README.md`
  - `docs/product/contracts/patch-plan-schema-v0-ko.md`
- 실제 상태:
  - `63f5f89`의 코드, 테스트, Docker/운영 파일
  - PR #7(M1), #8(M2), #10 이후 품질 수정, #14~#32 문서 수정 흐름의 Git 이력
  - PR #32 브랜치에 보존된 `AGENT_TEST_REPORT.md`와 `AGENT_REVIEW.md`
- 완료 판정:
  - 저장소에 구현이 있다는 것과 실제 베타 운영 설정/실파일 QA가 끝났다는 것을 구분한다.
  - PR 제목이나 설계 문서의 “베타 전 범위” 표현만으로 M1~M5 전체 완료를 추정하지 않는다.

## M1~M5 정확한 현재 상태

| 마일스톤 | 판정 | 완료된 근거 | 남은 항목 / 완료로 볼 수 없는 이유 |
|---|---|---|---|
| **M1 베타 차단 요소 해제** | **구현 완료** | PR #7 `63db6ae`: Google OAuth email allowlist, 게스트 제거와 로그인/동의 게이트, 전 사용자 라우트 `RequireAuth`, 4개 고비용 endpoint 크레딧 429, `text_chat` PII 마스킹, 스캔본 미지원 처리와 프론트 안내. 백엔드/AX/프론트 회귀 테스트가 존재한다. | 실제 `BETA_ALLOWED_EMAILS`, Google client ID 등 운영 값 주입은 M5/운영 준비다. 동의 버전 변경 시 로그인 유지 사용자의 재동의 누락은 전략 문서가 v1 베타에서 명시적으로 수용했다. |
| **M2 베타 스택 인프라** | **저장소 구현 완료 / 운영 가동 미완료·미검증** | PR #8 `c9d896d`: backend/AX/frontend Dockerfile, nginx 단일 origin, `docker-compose.beta.yml`, 분리된 DB/Redis/볼륨/포트, `.env.beta.example`, `scripts/beta_backup.sh`가 존재한다. | 저장소 이력에는 beta compose 실제 build/up smoke, ngrok static domain 연결, Google OAuth origin 등록, 백업 cron 및 restore 검증, 맥 sleep 방지/프로세스 재시작, 야간 배포 절차 실행 증거가 없다. 따라서 M2 전체를 완료로 표시하면 안 된다. |
| **M3 품질 마감** | **부분 완료** | PR #14~#31에서 HWP/PDF/버전/patch 흐름 결함을 다수 수정했다. PR #32 `63f5f89`는 DOCX 다중 매치의 침묵 오수정 방지, PDF post-render invariant 1~2, `ambiguous_anchor`/`render_validation_failed` usage-event 기록을 구현했다. 보존된 보고서 기준 `apps.documents` 306 tests 및 독립 리뷰 focused 15 tests가 통과했다. | 실제 업무 HWP 5~10개 검증 증거가 없고 `backend/apps/documents/fixtures/sample.hwp` 하나뿐이다. 5포맷 실파일 E2E QA 체크리스트/실행 기록 및 모바일 smoke가 없다. 가장 중요한 구현 갭은 **DocumentChange/DocumentVersion 실패 사유의 사용자 문구 매핑**이다. PR #32의 안정 코드는 `PatchResult`와 `UsageEvent.metadata`에만 남고, 사용자 API/화면에는 전달되지 않는다. |
| **M4 베타 재료** | **대부분 미착수** | 인터뷰 질문 7개는 클로즈드 베타 전략 문서 8절에 이미 있다. `.env.beta.example`에는 단일 LLM provider 설정 틀이 있다. | 배포용 샘플 3종(HWP 공문/XLSX 정산표/PDF 계약서), 한 장 가이드, 실제 sonnet/gpt 비교 실행 및 모델 확정 증거가 없다. 테스트 fixture `sample.hwp`는 사용자용 샘플 산출물이 아니다. |
| **M5 초대 시작** | **미착수** | allowlist 기능과 초대용 환경변수 템플릿은 준비돼 있다. | 실제 초대자 등록/링크 공유, 카톡 베타방, 4~6주 운영, 다운로드 완주 사용자 5명, 심층 인터뷰 5회 기록 증거가 없다. 예시 이메일이 든 `.env.beta.example`은 초대 실행 증거가 아니다. |

### PR #32 이후의 핵심 해석

- PR #32는 **아키텍처 문서 10.1의 backend 베타 전 실행 레이어 범위**를 닫았다. M1~M5 전체 또는 M3 전체를 닫은 PR은 아니다.
- `docs/product/README.md` 4절의 “DOCX/PPTX는 미리보기/후속 확장” 표현은 실제 `replace_text` patcher와 5포맷 텍스트 수정 베타 범위보다 보수적으로 남아 있다. 이후 문서 정합성 갱신이 필요하지만 다음 구현의 선행 blocker는 아니다.
- 실패 코드 계약이 분산돼 있다. 스캔 분석은 실제 코드/전략에서 `unsupported_scan`, 실행 레이어 설계 8절에서는 `unsupported_scan_pdf`를 사용한다. PR #32가 추가한 두 코드는 patch 결과에는 있으나 `DocumentChange`에 영속화되지 않는다.
- `DocumentChangeSerializer`는 `status`만 반환하고 실패 코드/문구가 없다. `DocumentVersionSummarySerializer`는 기존 `error_message`조차 반환하지 않는다. 프론트는 terminal version 상태를 보고 카드를 단순히 `failed`로 바꾸므로 사용자는 재시도, 요청 수정, 운영자 문의 중 무엇을 해야 하는지 알 수 없다.

## [Planning Agent]

### Requirement analysis

다음 단일 구현 태스크는 **“M3 patch 실패 사유 사용자 안내 vertical slice”**가 가장 적합하다.

이유:

1. 클로즈드 베타 계획 M3에 명시된 미완료 구현 항목이다.
2. PR #32가 안정 실패 코드를 만들었으므로 새 추상화 없이 바로 사용자 가치로 연결할 수 있다.
3. 실파일 HWP 확보와 전체 QA는 중요한 다음 gate지만 외부 파일/수동 실행 의존 작업이며 “단일 구현 태스크”로는 덜 적합하다.
4. M2의 남은 것은 주로 운영 실행/검증이고, M4/M5를 먼저 시작하면 실패한 사용자가 원인을 알 수 없는 상태로 베타가 열린다.

### Design strategy

예상 Workflow intensity: **Full Mode**. 작은 기능이지만 durable failure state를 위해 DB migration을 포함하는 안을 권장하므로 harness 규칙상 Full Mode다.

핵심 설계:

```text
PatchResult / task early failure
  → 안정 failure_code를 DocumentChange·DocumentVersion에 영속화
  → backend serializer가 allowlist mapping으로 안전한 한국어 failure_message 생성
  → terminal 상태에서 frontend가 최신 change/version 응답 재조회
  → 카드·버전 영역은 서버가 준 failure_message만 표시
```

- 코드와 사용자 문구를 분리한다.
- raw exception, 파일 경로, subprocess stderr는 `error_message`/로그/UsageEvent에만 두고 API에는 노출하지 않는다.
- 알 수 없는 코드와 기존 failed row의 빈 코드는 일반 안내 문구로 안전하게 fallback한다.
- `ambiguous_anchor`는 “생성 실패”가 아니라 요청에 위치 단서를 더해 재시도하도록 안내한다.
- `render_validation_failed`는 잘못된 artifact가 차단됐음을 알리고 재시도/문의 동선을 준다.
- 기존 `UsageEvent.metadata.reason` 관측 계약은 유지한다.

확정된 구현 세부 원칙:

- 두 모델의 `failure_code`는 `blank=True`, `default=""`인 additive `CharField`로 추가하고 과거 row는 backfill하지 않는다.
- serializer는 안정 코드와 서버가 allowlist로 만든 안전한 `failure_message`를 읽기 전용으로 반환한다. 프론트는 코드를 해석하거나 문구를 재구성하지 않는다.
- failed/needs-confirmation change는 `operation_id`별 결과 item의 code를 저장한다. code가 없는 기존 patch 실패는 `patch_failed`로 수렴한다.
- version 조기 실패는 현재 UsageEvent reason과 같은 `source_file_missing`, `unsupported_format`, `source_file_read_error`, `render_exception`을 사용한다. artifact 저장 실패에는 `artifact_save_error`를 부여한다.
- patch 결과의 대표 코드는 hard failure를 needs-confirmation보다 우선한다. 부분 성공인 `ready` version에도 대표 코드가 있으면 보존하되, UI는 change-level 안내를 우선하고 version 문구는 change-level 설명이 없는 조기/전체 실패의 fallback으로 사용한다.
- `ambiguous_anchor`는 실패가 아니라 `needs_confirmation` 의미를 유지한다.
- 스캔 분석 코드 불일치는 실제 코드·전략·UsageEvent 계약에 이미 쓰이는 `unsupported_scan`을 canonical 이름으로 삼고 문서의 `unsupported_scan_pdf`를 정정한다.

### Complexity estimation

- 시간/규모: 중간. backend migration + persistence + serializer + frontend terminal refresh/render + 양쪽 회귀 테스트.
- 계산 복잡도: change 수에 선형 `O(n)`. 기존 `persist_patch_result` 순회와 동일 차수다.
- 분기 위험: 코드별 문구 분기를 프론트에 복제하면 커진다. backend 단일 mapping table과 unknown fallback으로 제한한다.
- 데이터 위험: migration 자체는 nullable/blank default 추가로 비파괴적이어야 한다. 과거 failed row는 backfill하지 않고 generic fallback 처리한다.

## 제안 태스크의 Scope

### 포함

1. `DocumentChange`에 안정 `failure_code`를 저장하고 patch 결과의 `failed_items`/`needs_confirmation_items`를 operation_id 기준으로 정확히 연결한다.
2. version-level 조기 실패(`source_file_missing`, `unsupported_format`, `source_file_read_error`, `render_exception`)와 persist 결과의 대표 실패 코드를 `DocumentVersion.failure_code`에 저장한다.
3. code → 안전한 한국어 문구 mapping을 backend serializer 계층 한 곳에 둔다.
4. `DocumentChangeSerializer`와 `DocumentVersionSummarySerializer`에 읽기 전용 `failure_code`, `failure_message`를 추가한다. raw internal `error_message`는 반환하지 않는다.
5. patch terminal 상태(`ready`, `failed`, `needs_confirmation`) 도달 후 최신 DocumentChange를 조회해 프론트 suggestion과 동기화한다.
6. 변경 카드에는 change-level 안내를, 버전 탭/상태 영역에는 version-level fallback 안내를 표시한다.
7. 실패 코드 명명 불일치(`unsupported_scan` 대 `unsupported_scan_pdf`)를 하나의 canonical code로 정리하고 관련 계약 문서를 함께 갱신한다.

### 제외

- 실패 자체를 고치는 retry engine, 자동 fallback, 사용자 수동 anchor picker.
- DOCX resolver 클래스화, HWP wire contract, PDF invariant 3~4.
- OCR, T2 표/구조 수정, vision/image fallback과 PII 정책 결정.
- 5포맷 수동 QA 실행, 실제 HWP 5~10개 확보, 베타 샘플/가이드 제작.
- Sentry 또는 새 모니터링 시스템 도입.
- 기존 raw `error_message`를 사용자에게 직접 노출하는 것.

## Concrete file touchpoints

예상 production/config/docs touchpoint:

- `backend/apps/documents/models.py`
  - `DocumentChange.failure_code`, `DocumentVersion.failure_code` 추가.
- `backend/apps/documents/migrations/0015_*.py`
  - 두 모델에 blank/default 기반 비파괴 schema migration.
- `backend/apps/documents/patcher.py`
  - `persist_patch_result()`에서 operation별 code 영속화; code 없는 현재 실패는 canonical generic code로 수렴.
- `backend/apps/documents/tasks.py`
  - 조기 실패와 대표 patch 실패 code를 version에 영속화하되 기존 UsageEvent reason을 유지.
- `backend/apps/documents/serializers.py`
  - 단일 mapping table, status-aware unknown/legacy fallback, 읽기 전용 `failure_code`/`failure_message`.
- `frontend/src/api/documentChanges.js`
  - 이미 존재하는 change list endpoint의 version-filtered 조회 함수 추가.
- `frontend/src/pages/Workspace/WorkspaceCenter.jsx`
  - terminal 상태 후 최신 change 동기화 및 version-level 안내 전달.
- `frontend/src/utils/changeSuggestions.js`
  - `failure_message` normalization.
- `frontend/src/pages/Workspace/ChangeSuggestionCard.jsx`
  - failed/needs_confirmation 전용 actionable message 표시.
- `frontend/src/pages/Workspace/VersionTabs.jsx` 또는 인접 status component
  - version-level fallback message를 접근 가능한 형태로 표시.
- `docs/product/contracts/patch-plan-schema-v0-ko.md`
  - 실행 결과 API의 failure code/message 계약과 canonical naming 기록.
- `docs/product/architecture/document-edit-execution-layer-design-v1-ko.md`
  - 실제 canonical scan code와 사용자 노출 경계 정합화.

예상 test touchpoint:

- `backend/apps/documents/tests_patcher_pure.py`
- `backend/apps/documents/tests_docx_pptx_patcher.py`
- `backend/apps/documents/tests_pdf_patcher.py`
- `backend/apps/documents/tests_usage_event.py`
- 신규 또는 기존 serializer/API test 모듈(가급적 `backend/apps/documents/tests_patch_api.py` / `tests_version_api.py`)
- `frontend/tests/test_changeSuggestions.mjs`
- `frontend/tests/ChangeSuggestionCard.test.jsx`
- `frontend/tests/WorkspaceCenterVersionCards.test.jsx`
- `frontend/tests/VersionTabs.test.jsx`

## 주요 리스크와 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| migration이 기존 베타 DB를 깨뜨림 | 배포 차단/데이터 위험 | blank default의 additive field만 사용, migration test 및 beta compose DB에서 migrate smoke/rollback 계획 확인 |
| `failed_items`의 code/reason이 persist 중 유실 | 카드가 다시 generic 실패만 표시 | operation_id별 저장을 단위 테스트하고 부분 성공/동반 실패를 포함 |
| raw exception/경로가 API로 노출 | 보안·신뢰 문제 | serializer는 allowlist 문구만 반환하고 unknown은 generic; `error_message` 필드 미노출 회귀 테스트 |
| 프론트가 생성 당시 `localPatchData`만 계속 사용 | backend의 최신 code가 화면에 반영되지 않음 | terminal 상태 후 version_id 필터로 change list 재조회, stale response/race 방어 |
| `ambiguous_anchor`를 실패로 뭉갬 | 사용자가 불필요하게 재시도하거나 신뢰 상실 | `needs_confirmation`과 별도 문구/스타일 유지 |
| code taxonomy drift | backend/analytics/UI 의미 불일치 | canonical 상수/문서 정리, UsageEvent reason 회귀 테스트 |
| legacy/unknown code | 빈 화면 또는 프론트 분기 폭증 | backend generic fallback, 프론트는 문구 해석 금지 |

## [Test Agent]

### Test strategy

- TDD 순서: backend persistence/API Red → migration/implementation Green → frontend render/refresh Red → Green.
- backend는 상태와 계약을 검증하고, frontend는 서버 문구를 그대로 표시하는지만 검증한다.
- 개발 compose에는 backend service가 없으므로 focused test는 `backend/.venv`에서 실행할 수 있다. 최종 Full Mode validation에서는 beta Docker image/compose로 migration 및 동일 backend test 실행을 우선한다. 불가능하면 사유를 명시한다.

### Test cases

- **Happy**
  - 성공 change/version은 `failure_code`가 비고 `failure_message`도 비어 있다.
  - `render_validation_failed`가 change/version에 영속화되고 안전한 한국어 문구로 직렬화된다.
  - terminal refresh 뒤 카드와 버전 UI가 서버 문구를 표시한다.
- **Boundary**
  - 과거 failed row처럼 code가 비어 있거나 unknown code인 경우 generic 문구를 반환한다.
  - ready 부분 성공 version은 대표 코드를 보존하되 change-level 안내를 우선하며, 성공 change에는 실패 문구가 붙지 않는다.
  - 부분 성공에서 applied/failed/needs_confirmation change의 code와 표시가 서로 섞이지 않는다.
  - 동일 결과물 동반 중단 항목도 operation_id별 code를 가진다.
  - terminal fetch 응답이 늦게 도착하거나 화면이 다른 upload/version으로 전환되면 stale state를 적용하지 않는다.
- **Failure**
  - `source_file_missing`, `unsupported_format`, `source_file_read_error`, `render_exception`은 version-level safe message를 반환한다.
  - `ambiguous_anchor`는 failed가 아니라 needs_confirmation 안내를 반환한다.
  - serializer 응답에 raw exception text, 로컬 파일 경로, stderr가 포함되지 않는다.
- **Regression**
  - PR #32의 `UsageEvent.metadata.reason` 값이 유지된다.
  - 기존 applied/rejected/ready UI와 다운로드 흐름이 변하지 않는다.
  - PDF validation 실패 시 artifact 미생성, DOCX 다중 매치 시 무변형/NEEDS_CONFIRMATION 동작이 유지된다.

예상 실행:

```bash
cd backend
./.venv/bin/python manage.py test \
  apps.documents.tests_patcher_pure \
  apps.documents.tests_docx_pptx_patcher \
  apps.documents.tests_pdf_patcher \
  apps.documents.tests_patch_api \
  apps.documents.tests_version_api \
  apps.documents.tests_usage_event \
  --settings=config.settings_test

./.venv/bin/python manage.py test apps.documents --settings=config.settings_test

cd ../frontend
npm test -- --run
npm run build
```

최종 beta Docker validation 후보:

```bash
docker compose -f docker-compose.beta.yml --env-file .env.beta build backend-web nginx
docker compose -f docker-compose.beta.yml --env-file .env.beta run --rm backend-web \
  python manage.py migrate --check
docker compose -f docker-compose.beta.yml --env-file .env.beta run --rm backend-web \
  python manage.py test apps.documents --settings=config.settings_test
```

## Acceptance criteria

1. 모든 현재 patch terminal 경로가 durable canonical `failure_code`를 version에 남긴다.
2. change별 결과가 있는 경로는 operation_id 기준으로 올바른 `DocumentChange.failure_code`를 남긴다.
3. change/version API는 안정 `failure_code`와 backend mapping의 한국어 `failure_message`를 제공하고 raw 내부 오류는 제공하지 않는다.
4. unknown/legacy code는 비어 있지 않은 generic 안전 문구로 표시된다.
5. `ambiguous_anchor`와 hard failure가 화면에서 의미와 행동 지침이 다르게 보인다.
6. terminal patch 후 새로고침 없이 최신 실패 안내가 카드 또는 version 상태 영역에 나타난다.
7. 부분 성공에서 성공/실패/확인 필요 항목의 상태와 문구가 정확히 분리된다.
8. 기존 UsageEvent reason, artifact 차단, 버전 다운로드, change 상태 전이 회귀 테스트가 통과한다.
9. backend 전체 documents test, frontend 전체 test/build, migration validation 결과가 기록된다.
10. 계약 문서의 code 이름과 실제 상수/API가 일치한다.

## Sequencing / 다음 gate

1. Orchestrator가 Full Mode용 새 worktree를 만들고 기준 커밋 및 dirty-state handoff를 확인한다.
2. backend Red tests → additive migration/model → patcher/task persistence → serializer mapping.
3. backend focused tests 후 frontend Red tests → terminal refresh → 카드/버전 문구 표시.
4. contract/architecture naming 정합화.
5. backend/frontend 전체 test 및 beta Docker migration/build validation.
6. 독립 Review와 Validation 통과 후에만 merge readiness 판정.
7. 이 task가 merge되면 M3의 다음 gate는 **실제 HWP 5~10개 확보 + 5포맷 실파일 QA 체크리스트 실행**이다. 발견 버그만 별도 TDD 구현 task로 분리한다.

## Grilling conclusion

- 결정 1: additive `failure_code` migration을 허용한다 — **승인됨**.
- 위임 범위: 이 vertical slice에 기술적으로 필요한 모델, migration, persistence, API, frontend, test, 문서 변경 — **엔지니어링 판단에 위임됨**.
- 코드 탐색으로 해소된 항목: 기존 change list API의 `version_id` 필터 재사용, hard failure 우선의 대표 코드 선택, terminal 상태(`ready`/`failed`/`needs_confirmation`) 후 재조회, legacy/unknown generic fallback.
- 남은 material product/scope decision: **없음**.
- 따라서 grilling은 종료하며 이 계획을 확정한다.

## Finalized implementation handoff

- 태스크명: **M3 patch 실패 사유 사용자 안내 vertical slice**
- Workflow intensity: **Full Mode** (additive DB migration 포함).
- 구현 경계: 위 Scope의 포함 항목만 수행하고 제외 항목은 확장하지 않는다.
- 시작 조건: orchestrator가 harness 규칙에 맞는 새 worktree를 준비한다. 현재 `main` 작업트리에서 production code를 수정하지 않는다.
- 구현 우선순위: durable code 영속화 → 안전한 serializer contract → terminal refresh/UI 표시 → taxonomy 문서 정합화.
- 필수 품질 gate: focused TDD, backend documents 전체 test, frontend 전체 test/build, migration validation, 가능한 경우 beta Docker build/test, 독립 Review, 최종 Validation.
- 보안 경계: raw `error_message`, exception, 로컬 경로, subprocess stderr는 API/UI에 노출하지 않는다.
- 완료 기준: 위 Acceptance criteria 10개를 모두 증거와 함께 충족한 뒤에만 merge-ready로 판단한다.
