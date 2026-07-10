# AGENT_REVIEW.md

[Review Agent]

## 검토 범위

- 대상 worktree: `/Users/haram/Desktop/office-ax-worktrees/document-edit-execution-layer`
- 대상 브랜치/커밋: `work/document-edit-execution-layer` through `3ca7351`
- 기준 범위: `docs/product/architecture/document-edit-execution-layer-design-v1-ko.md` 10.1 베타 전 범위 중 backend 구현분
- 먼저 확인한 문서: `AGENT_TEST_REPORT.md`
- 주요 검토 파일:
  - `backend/apps/documents/patcher.py`
  - `backend/apps/documents/tasks.py`
  - `backend/apps/documents/tests_docx_pptx_patcher.py`
  - `backend/apps/documents/tests_pdf_patcher.py`
  - `backend/apps/documents/tests_usage_event.py`

## Findings

Blocking finding 없음.

이번 변경은 10.1 범위의 세 축(DOCX 다중 매치 침묵 처리 수정, PDF render validation invariant 1~2 smoke check, 실패 사유 코드 usage event wiring)에 맞게 제한되어 있고, 검토 범위 안에서 merge를 막을 버그나 회귀는 확인하지 못했다.

## SOLID compliance

양호.

- `patcher.py`의 기존 3단계 구조(`collect_applied_changes` / `render_*` / `persist_patch_result`)를 유지했다.
- PDF 검증은 `_validate_pdf_render`, `_validate_pdf_text_change`, `_find_unexpected_empty_page`로 분리되어 `render_pdf`의 책임을 과도하게 키우지 않았다.
- 실패 사유 코드 상수는 patcher가 직접 발급하는 코드로 제한되어 있다.

## OOP structure

양호.

- 이번 범위는 설계 10.1의 "resolver 추상화 없이 기존 NEEDS_CONFIRMATION 패턴 재사용" 조건을 지킨다.
- DOCX resolver 클래스화, TargetResolver wire contract 정식화, DOCX/HWP render validation은 10.2 범위로 남겨둔 것이 설계 문서와 일치한다.

## Branching complexity

허용 가능.

- `render_docx`는 `0개 / 1개 / 2개 이상` 분기가 명확하며, 빈 `text_match`를 조기 실패로 처리해 기존 임의 삽입 결함을 줄였다.
- `render_pdf`는 `RESOLVED / AMBIGUOUS / 실패` 분기를 유지하고, 적용 후 검증 실패 시 artifact 전체를 실패 처리하는 정책이 단일 bytes 산출물 특성과 일치한다.
- `_primary_failure_code`는 `failed_items` 우선, 그 다음 `needs_confirmation_items`를 확인하는 단순 우선순위라 이벤트 metadata 의미가 예측 가능하다.

## Test adequacy

양호.

- DOCX 다중 매치: 단락 간 중복, 단락 내 중복, task 상태 전이, 부분 성공, 빈 `text_match` 경계를 포함한다.
- PDF render validation: replacement 미추출, original 잔존, 페이지 수 변화, 예상 밖 빈 페이지, 빈 replacement 삭제형 redact, 혼합 실패, task 경로 상태 전이를 포함한다.
- usage event: `ambiguous_anchor`, `render_validation_failed`, 코드 없는 실패에서 `reason` 미기록 경계를 포함한다.
- Docker 미실행은 `AGENT_TEST_REPORT.md`에 근거가 적혀 있고, 현재 `settings_test`가 SQLite in-memory + Celery eager로 해당 순수 render/ORM 경로를 검증한다는 설명은 수용 가능하다. Docker backend 이미지 검증은 beta 스택 최종 검증 단계에서 추가로 판단하면 된다.

## Complexity validation

통과.

- PDF 검증은 pixel diff가 아니라 `build_pdf_document_layout` 재사용 기반 구조 검증으로 제한되어 설계 7.1/10.1과 맞다.
- 같은 줄 대역을 page right까지 넓게 잡는 replacement 검증은 오탐을 줄이는 보수적 smoke check다. 같은 줄 먼 위치의 동일 replacement로 인한 미탐 가능성은 남지만, 테스트 보고서에 명시된 수용 리스크이고 10.1 smoke check 범위를 넘는 blocker로 보지 않는다.
- invariant 3~4(rect 겹침, 과대 영역), DOCX/HWP render validation, vision fallback은 구현하지 않았고 10.2 범위와 일치한다.

## Error handling structure

양호.

- 예측 가능한 업무 실패는 `PatchResult.failed_items`와 `needs_confirmation_items`로 귀결된다.
- render 단계 예외는 기존 `patch_document_version`의 `render_exception` 경계에서 처리된다.
- 검증 실패는 artifact를 저장하지 않고 `render_validation_failed` 코드로 수렴한다.
- DOCX ambiguous는 FAILED가 아니라 NEEDS_CONFIRMATION으로 분리되어 UX 의미가 유지된다.

## Test execution result

리뷰어가 독립 실행:

```text
./.venv/bin/python manage.py test apps.documents.tests_docx_pptx_patcher.DocxAmbiguousMatchTest apps.documents.tests_pdf_patcher.PdfRenderValidationTest apps.documents.tests_usage_event.PatchArtifactFailureCodeTest --settings=config.settings_test
Ran 15 tests in 1.972s
OK
```

```text
./.venv/bin/python manage.py test apps.documents --settings=config.settings_test
Ran 306 tests in 21.614s
OK
```

참고: `python manage.py ...`는 이 환경에서 `python` 명령이 없어 실패했고, `python3`는 Django가 설치되지 않은 system interpreter라 실패했다. 최종 검증은 보고서와 동일하게 `backend/.venv/bin/python`으로 수행했다.

## Merge readiness judgment

Merge ready.

검토 범위 안에서 blocking issue 없음. 테스트는 통과했고, 남은 리스크는 10.1 smoke check의 의도된 한계 또는 10.2 범위 항목이다.

## Reusable failure pattern note

이번 리뷰에서 `AGENT_FAILURES.md`에 남길 재사용 실패 패턴은 확인되지 않았다.
