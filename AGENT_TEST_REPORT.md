# AGENT_TEST_REPORT.md

## Scope

`document-edit-execution-layer-design-v1-ko.md` 10.1절 베타 전 범위 중 backend 구현분
(AGENT_PLAN.md 기준). T2·구조 수정·vision fallback은 범위 밖 유지.

브랜치: `work/document-edit-execution-layer`

## 구현 요약 (커밋 순)

| 커밋 | 내용 |
|---|---|
| `ff330f0` | test: DOCX 다중 매치 회귀 테스트 (Red) |
| `39ebc01` | fix: `render_docx` 다중 매치 → NEEDS_CONFIRMATION (Green) |
| `03440bd` | test: PDF post-render 검증 실패 케이스 테스트 (Red) |
| `aadc1c4` | feat: PDF post-render 구조 검증 — invariant 7.1 1~2항 (Green) |
| `735d8fc` | test: patch 실패 usage event 사유 코드 테스트 (Red) |
| `88a6deb` | feat: usage event metadata에 안정 실패 사유 코드 wiring (Green) |

### 슬라이스 1 — DOCX 다중 매치 (patcher.py `render_docx`)

- 변형 전에 문서 전체(단락 간 + 단락 내) `text_match` 발생 횟수를 계수.
  0개=기존 failed 유지 / 1개=기존 교체 동작 유지 / 2개 이상=변형 없이
  `needs_confirmation_items`에 `code: "ambiguous_anchor"` 기록.
- 기존 `PatchResult.needs_confirmation_items`·`persist_patch_result` 상태 처리 재사용
  (DOCX resolver 추상화 없음 — 계획 3단계 준수).
- 경계 수정: 빈 `text_match`는 모든 단락에 매치되어 임의 삽입되던 동작을
  명시적 `failed_items`로 전환.
- 실패 사유 코드 상수 신설: `FAILURE_CODE_AMBIGUOUS_ANCHOR`,
  `FAILURE_CODE_RENDER_VALIDATION_FAILED` (design 8절). human-readable `reason` 유지.

### 슬라이스 2 — PDF post-render 검증 (patcher.py `render_pdf` + 헬퍼 3종)

- 적용 성공 change의 (change, page, rect)를 `applied_records`로 보존, `doc.save()` 후
  수정본 bytes를 `_validate_pdf_render()`로 재검증.
- invariant 2: 수정본 열림(예외 없음), 페이지 수 유지, 원래 token이 있던 페이지의
  예상 밖 빈 페이지 검출 (빈 replacement 삭제형 redact가 적용된 페이지는 면제).
- invariant 1: redact/replace 계열 change마다 `build_pdf_document_layout` token 추출을
  재사용해 replacement가 rect 근처 같은 줄 대역에서 재추출되는지 + original이 rect
  자리에서 사라졌는지 확인. 공백 제거 비교(오탐 방지), replacement ⊇ original
  케이스('6'→'6월')는 잔존 검사 생략.
- 검증 실패 시: artifact 미생성(수정본 bytes에 전 변형이 섞여 부분 성공 불가),
  직접 실패 항목은 구체 사유 + `code: "render_validation_failed"`, 동반 applied 항목은
  "함께 중단" 사유로 전원 failed 전환 → version FAILED.
- invariant 3~4(rect 겹침·과대 영역), DOCX/HWP 렌더 검증은 범위 밖(10.2절).
- 부수 정리: PDF AMBIGUOUS 경로 `needs_confirmation_items`에도
  `code: "ambiguous_anchor"` 부여 (DOCX와 코드 체계 통일).

### 슬라이스 3 — usage event wiring (tasks.py)

- `patch_document_version` 최종 실패 이벤트에
  `reason=_primary_failure_code(result)` 추가 — 조기 실패 경로(`source_file_missing`
  등)와 동일한 `metadata.reason` 키 사용.
- `_primary_failure_code`: `failed_items` 코드 우선, 없으면
  `needs_confirmation_items` 코드, 둘 다 없으면 None(키 미기록 — 기존 동작 보존).

## TDD 사이클 기록

세 슬라이스 모두 Red → Green 순서 준수, Red/Green 별도 커밋.

- Red 1 (DOCX): 5건 assertion 실패 — `AssertionError: Lists differ: ['op_docx_dup_01'] != []`,
  `'applied' != NEEDS_CONFIRMATION` (침묵 첫 매치 결함 재현). import/컴파일 오류 아님.
- Red 2 (PDF): 6건 assertion 실패 — `['op_pdf_val_01'] != []` 등 (검증 부재 재현).
  경계 1건(빈 replacement 삭제형 redact)은 현행 동작 보존 확인용으로 Red에서도 통과.
- Red 3 (usage event): 2건 assertion 실패 — `None != 'ambiguous_anchor'`,
  `None != 'render_validation_failed'`. 경계 1건(코드 없는 실패 → reason 키 없음) 통과.
- Green: 각 슬라이스 신규 테스트 전건 통과, 테스트 약화·삭제 없음.

## 추가/변경 테스트

- `tests_docx_pptx_patcher.py` — `DocxAmbiguousMatchTest` 5건:
  단락 간 중복 / 단락 내 중복(경계) / task 경로 상태 전이 / 혼합 부분 성공
  (모호 항목 원문 무변형 검증 포함) / 빈 text_match(경계)
- `tests_pdf_patcher.py` — `PdfRenderValidationTest` 7건 + 기존 모호성 테스트에
  code assertion 보강: 삽입 누락 / redaction 누락 / 페이지 수 변화 / 예상 밖 빈 페이지 /
  삭제형 redact 통과(경계) / 혼합 시 artifact 미생성 / task 경로 version FAILED
- `tests_usage_event.py` — `PatchArtifactFailureCodeTest` 3건:
  DOCX ambiguous → `reason=ambiguous_anchor` / PDF 검증 실패 →
  `reason=render_validation_failed` / 코드 없는 실패 → reason 키 미기록(경계)

관점 커버: happy(기존 유지 + 혼합 부분 성공), boundary(단락 내 중복, 빈 text_match,
빈 replacement, 코드 없는 실패), failure(검증 4종, 상태 전이), regression(침묵 첫 매치,
"검게 칠했는데 안 들어감" PR #29 계열, 기존 CJK·fragmented happy path 오탐 없음).

## 테스트 실행 결과

```
python manage.py test apps.documents --settings=config.settings_test
Ran 306 tests in 20.847s — OK
```

포커스 모듈: tests_docx_pptx_patcher 15/15, tests_pdf_patcher 24/24,
tests_usage_event 23/23, tests_patcher_pure 12/12.

### 실행 환경 (Docker 예외 사유)

호스트 venv(`backend/.venv`, Python 3.11 + Django 5.0.6) 실행.
개발용 `docker-compose.yml`에는 backend 서비스가 없고(postgres/redis만) backend 개발
런타임은 호스트 venv다. `settings_test`는 SQLite in-memory + Celery eager로 외부
서비스 의존이 없어 컨테이너와의 환경 차이가 테스트 대상 경로(순수 렌더 함수,
SQLite ORM)에 영향을 주지 않는다. Docker 검증이 필요하면 beta 스택
(`docker-compose.beta.yml`) backend 이미지 빌드 후 동일 명령 실행 가능 — orchestrator
판단에 위임.

## 리뷰 참고 사항

- `render_pdf` 검증 실패 시 정상 항목까지 전부 FAILED 처리하는 것은 의도된 설계
  (artifact가 단일 bytes라 부분 성공 불가). 동반 중단 항목도 동일 코드
  `render_validation_failed`를 갖되 reason 문자열로 구분된다.
- invariant 1 검증은 overapproximation 대역(rect 좌 -2pt ~ 페이지 우측 끝, 상하
  ±font_size)을 사용 — 삽입 텍스트 폭을 사전에 알 수 없기 때문. 오탐(정상을 실패로)
  방지를 우선했고, 같은 줄 먼 위치의 동일 문구로 인한 미탐 가능성은 smoke check
  범위로 수용 (설계 7절 "pixel diff는 하지 않는다"와 동일 논리).
- 빈 `text_match` 실패 전환은 기존 동작 변경이나, 변경 전 동작(첫 단락 임의 삽입)은
  명백한 결함으로 판단해 다중 매치 수정 범위에 포함.
