# AGENT_TEST_REPORT — PDF readable text edit MVP

## 변경 요약

- `backend/apps/documents/tasks.py`: `_OPERATIONS_BY_FORMAT["pdf"]`에 `replace_text`
  추가. 스키마 문서(`docs/product/contracts/patch-plan-schema-v0-ko.md` 6절)는 PDF
  readable의 `replace_text`를 "짧은 overlay 치환"으로 명시적으로 허용하고,
  `patcher.py`의 `render_pdf`는 `annotate`가 아닌 모든 operation을 이미
  `redact_overlay`와 동일한 방식(`_apply_pdf_redact_overlay`)으로 렌더링하고
  있었다. 하지만 `collect_applied_changes` 호출 시 넘기는 operation 필터
  목록에서 `replace_text`가 누락되어 있어, LLM이 PDF에 대해 `replace_text`를
  생성해도 DB 조회 단계에서 통째로 걸러지고 버전이 모호한 사유
  ("적용 가능한 변경 항목이 없습니다")로 실패했다. 렌더링 로직 변경 없이
  필터 목록 1줄만 수정.
- `backend/apps/documents/tests_pdf_patcher.py`: 회귀 테스트
  `PdfReplaceTextTest` 추가 (2개), CJK 소스 텍스트 생성용 헬퍼
  `_build_pdf_bytes_cjk` 추가.

## TDD 사이클

### Red

`PdfReplaceTextTest.test_replace_text_via_task_sets_version_ready`,
`test_replace_text_korean_short_replacement_is_extractable` 작성 후 수정 전
코드로 실행 → 실제 assertion 실패 확인:

```
AssertionError: 'failed' != DocumentVersion.Status.READY : text_match + replace_text 성공 후 version.status는 READY여야 한다
```

(import/compile 오류가 아닌 실제 상태값 불일치로 인한 실패임을 확인)

### Green

`tasks.py`의 `_OPERATIONS_BY_FORMAT["pdf"]`에 `"replace_text"` 추가 → 동일
테스트 재실행 시 최초 1차 통과 시도에서 `text_match` anchor가 원본 PDF에서
타겟 텍스트를 찾지 못해 실패(이유: 테스트 픽스처가 CJK를 Helvetica로 삽입해
검색 불가능한 텍스트였음 — 프로덕션 버그 아닌 테스트 픽스처 문제). `korea-s`
폰트로 원본 텍스트를 삽입하는 `_build_pdf_bytes_cjk` 헬퍼로 교체하고, 여러
단어 anchor가 PyMuPDF `search_for()`에서 단어 경계별로 rect가 분할 반환되는
문제를 피하기 위해 단일 한글 단어(`접수번호` → `접수완료`)로 anchor를
단순화한 뒤 재실행 → 통과.

### Refactor

추가 리팩터링 불필요 (변경 범위가 필터 목록 1줄 + 테스트 파일에 한정됨).

## 테스트 실행 결과

실행 환경: host-local (`backend/.venv`). 이 저장소의 `docker-compose.yml`은
postgres/redis 인프라만 컨테이너화하고 Django 앱 자체는 host에서 직접
실행하는 구조이므로(별도 backend Dockerfile 없음) host-local 실행이
repo-normal 경로임. postgres/redis 컨테이너(`office-ax-postgres-1`,
`office-ax-redis-1`)는 기동 중인 상태를 사용.

### `apps.documents.tests_pdf_patcher` (11 tests) — PASS

```
Ran 11 tests in 1.485s
OK
```

기존 annotate/redact_overlay 테스트(9개) 회귀 없음 + 신규 replace_text
테스트(2개) 통과.

### `apps.documents.tests_pdf_patcher apps.documents.tests_version_api` (27 tests) — PASS

```
Ran 27 tests in 3.599s
OK
```

### `apps.documents` 전체 (222 tests) — 4개 실패, PDF 변경과 무관 (범위 외)

```
Ran 222 tests in 24.488s
FAILED (failures=4)
```

실패 목록:

- `XlsxE2EHappyPathTest.test_full_xlsx_loop`
- `XlsxE2EOriginalMismatchTest.test_mismatch_change_fails_rest_succeeds`
- `XlsxE2ESalesScenarioTest.test_sales_table_scenario_partial_failure_preserves_success`
- `XlsxE2EVersionNumberRegressionTest.test_second_version_has_incremented_number_and_does_not_affect_first`

모두 `tests_e2e_xlsx_loop.py`의 XLSX 시나리오이며, `version.status`가
`generating`에 머물러 있거나(`READY` 기대) change 상태가 `applied`로 남아
있는(`FAILED` 기대) 형태의 실패다. 이번 변경은 `tasks.py`의
`_OPERATIONS_BY_FORMAT["pdf"]` 항목과 PDF 테스트 파일만 건드렸고 XLSX 경로
(`render_xlsx`, `_OPERATIONS_BY_FORMAT["excel"]`, `collect_applied_changes`
공용 로직 자체는 무수정)에는 관여하지 않는다. 실패 패턴이 Celery 태스크
비동기 처리/타이밍 또는 XLSX 전용 로직에 기인한 것으로 보이며 PDF
operation 필터 변경과 인과관계가 없다. orchestrator 지시에 따라 범위 외로
간주하고 별도 이슈로 남긴다 — 이번 태스크의 병합 게이트로 취급하지 않는다.

## 프론트엔드

- `frontend/src`에서 `replace_text`/`redact_overlay` 등 raw operation 문자열이
  사용자 노출 라벨로 쓰이는 곳 없음 확인 (`changeSuggestions.js`는 `operation`
  필드를 diff/스타일 요약 분기용으로만 보존하고, 카드 제목은 BE가 생성한
  `title`을 그대로 사용). 계획 문서의 "기존 UI가 이미 만족하면 프론트엔드
  변경 없음" 조건에 해당하여 프론트엔드 코드 변경 없음.
- `npm test`(`vitest run`) 결과: 17개 파일 중 16개 파일 / 104개 테스트 전부
  통과. `tests/PdfViewer.test.jsx` 1개 파일은 sandbox 경로 제한으로
  `@rhwp/core/rhwp_bg.wasm`(메인 체크아웃 `node_modules` 경로, worktree 밖)
  로드가 거부되어 테스트 자체가 실행되지 못함 — 이번 변경으로 건드린 파일과
  무관한 환경 제약이며, 이 worktree의 `node_modules`가 심볼릭하게 메인
  체크아웃을 참조하는 구조에서 기인한다.

## 미해결/후속 제안 (범위 외, 참고용)

- `render_pdf`의 `_apply_pdf_redact_overlay`는 replacement 텍스트가 redact
  영역(bbox) 폭을 넘어서는지 검증하지 않는다. AGENT_PLAN.md는 "text not
  fitting target bbox" 실패 사유 명시를 언급하지만, 이는 기존 동작을 바꾸는
  business validation 추가(트레이드오프 존재 — 엄격 검증 시 기존에 "성공"
  처리되던 overlay가 실패로 바뀔 수 있음)이므로 ask-policy.md에 따라 별도
  확인 없이 구현하지 않았다. Required Tests 목록에도 해당 항목은 없다.
- anchor 해석 실패 사유는 기존 코드에서 이미 명확함
  (`f"PDF anchor 해석 실패: {change.anchor}"`, 기존
  `test_anchor_miss_sets_change_failed`로 커버).

## Tester 독립 검증 (commit a356bfe)

구현자 리포트와 독립적으로 아래 명령을 재실행해 결과를 확인했다.

### 백엔드

```
cd backend
.venv/bin/python manage.py test apps.documents.tests_pdf_patcher apps.documents.tests_version_api --settings=config.settings_test
```

결과: `Ran 27 tests in 2.995s` / `OK`. 리뷰어가 확인한 `config.settings_test`
경로 사용(환경변수 probing 불필요). anchor 실패 케이스(`op_fail_*`,
`op_partial_01`)의 stderr 로그 출력은 의도된 실패 경로 로깅이며 테스트
실패가 아님.

### 프론트엔드

```
cd frontend
npm test
```

결과: `Test Files 1 failed | 16 passed (17)` / `Tests 104 passed (104)`.
실패한 1개 파일은 보고서에 기재된 것과 동일한 `tests/PdfViewer.test.jsx`
샌드박스 제약 재현: `Denied ID
/Users/haram/Desktop/office-ax/frontend/node_modules/@rhwp/core/rhwp_bg.wasm`
— 워크트리 `node_modules`가 메인 체크아웃을 참조하며 해당 경로가 워크트리
샌드박스 밖이라 vite가 모듈 로드를 거부한다(테스트 0개 실행, 실질 assertion
실패 아님). 이번 변경(`tasks.py` 필터 1줄, PDF 테스트 파일)과 무관.

### 결론

**PASS** — Required Tests(`tests_pdf_patcher`, `tests_version_api`) 27/27
통과, 프론트엔드 실질 테스트 104/104 통과. `PdfViewer.test.jsx` 실행 불가는
알려진 환경 제약(샌드박스 경로 제한)이며 코드 결함이 아니므로 병합 게이트로
간주하지 않는다. XLSX e2e 4건 실패는 별도 이슈로 이미 범위 외 처리되어
있으며 재확인하지 않았다(PDF 변경과 무관함이 코드상 명백 — `tasks.py` diff가
`_OPERATIONS_BY_FORMAT["pdf"]` 한 줄만 수정).

블로커 없음.
