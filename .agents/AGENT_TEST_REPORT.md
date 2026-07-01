# Implementer Test Report

_Updated: ownership taken over the full current worktree diff, including the
formula-token validation/bounds hardening added after the initial report below
(see "Hardening update" section for what changed and what was re-verified)._

## Scope implemented

Worktree: `/Users/haram/Desktop/office-ax-worktrees/next-roadmap-xlsx-ops` (`work/next-roadmap-xlsx-ops`). No changes made outside this worktree.

1. **PDF CJK `redact_overlay` stabilization** — already fixed in this branch (`fontname="korea-s"` in `_apply_pdf_redact_overlay`, `backend/apps/documents/patcher.py`). Confirmed via `PdfRedactOverlayTest`; no code change needed.
2. **XLSX `set_number_format`** — new `validate_xlsx_number_format_change` / `apply_xlsx_number_format` in `patcher.py`. `anchor.type=cell_range`, required `patch.expected_context` (reuses the `set_cell_style` range/context validation, extracted into shared helpers `_validate_xlsx_range` / `_validate_xlsx_range_expected_context`), `patch.number_format` whitelist (`yyyy-mm-dd`, `yyyy. mm. dd`, `#,##0`, `#,##0원`, `#,##0.00`, `0.0%`, `0.00%`), same 200-cell range cap as `set_cell_style`.
3. **XLSX `set_formula`** — new `validate_xlsx_formula_change` / `apply_xlsx_formula` / `_validate_xlsx_formula` in `patcher.py`. Single-cell only (`anchor.type=cell`; `cell_range` rejected), required `expected_context` (validated against the whole sheet, not bounded to the target cell, since the target cell is normally still empty — expected_context here confirms the *data being summed*, not the formula cell). Formula whitelist: `SUM/AVERAGE/COUNT/COUNTA/MIN/MAX/IF` (nesting allowed). Rejects: external sheet/workbook refs (`!`, `[...]`), URLs, string concat (`&`), unknown/forbidden functions (`INDIRECT`, `HYPERLINK`, `WEBSERVICE`, etc.), malformed formulas (unbalanced parens, no function call).
4. **All predictable validation failures surface as `PatchResult.failed_items`**, never raised exceptions — same pattern as existing `set_cell_style`.
5. **`_OPERATIONS_BY_FORMAT["excel"]`** in `tasks.py` extended to include `set_number_format`, `set_formula` so `patch_document_version` picks them up.
6. **Schema/prompt/persistence**:
   - `docs/patch_plan_schema.md`, `docs/product/patch-plan-schema-v0-ko.md` updated with new operations, anchors, patch whitelist tables, and payload examples.
   - `_PATCH_PLAN_SYSTEM_PROMPT` in `views.py` extended with rules for both new operations (whitelist values spelled out, forbidden formula patterns listed explicitly).
   - `GeneratePatchPlanView._create_changes` now merges `expected_context` into `patch.expected_context` for `set_cell_style`, `set_number_format`, and `set_formula` (was `set_cell_style`-only before), via new `_XLSX_FORMAT_OPERATIONS` constant.
7. **`ChangeSuggestionCard.jsx`** — generalized the `set_cell_style`-only summary branch into a `SUMMARY_LABEL_BY_OPERATION` map covering `set_cell_style` / `set_number_format` (`"표시 형식 X로 변경"`) / `set_formula` (`"수식 X 설정"`), so these operations show a summary sentence instead of an empty diff row. `anchorLabel` already handled `cell`/`cell_range` anchors, no change needed there.
8. **E2E**: added `XlsxE2ESalesScenarioTest` to `tests_e2e_xlsx_loop.py` — full upload → patch-plan → accept-all → patch → download loop with `set_cell_style` + `set_number_format` + `set_formula` all applied together, plus one intentionally-invalid `set_number_format` op to verify partial failure isolation and artifact correctness via `openpyxl`.

## Hardening update (ownership taken over post-report changes)

The following changes landed in the worktree after the initial report above and are now owned/verified as part of this report:

1. **Sheet-bounds hardening** in `_validate_xlsx_range` (`patcher.py`) — `set_cell_style`/`set_number_format` ranges are now also rejected if they fall outside Excel's real max columns/rows (`_XLSX_MAX_COLUMNS=16384`, `_XLSX_MAX_ROWS=1048576`), in addition to the existing 200-cell cap. Same bound added to `validate_xlsx_formula_change`'s target-cell check. New reason string: `"range가 XLSX 허용 범위를 벗어남"` / `"anchor.cell이 XLSX 허용 범위를 벗어남"`.
2. **Tokenizer-based formula hardening**: new `_validate_xlsx_formula_tokens` uses `openpyxl.formula.tokenizer.Tokenizer` as a second validation pass after the regex/whitelist pass, to catch shapes the regex alone can't reliably reject:
   - trailing/adjacent tokens after a complete value (`=SUM(D2:D2) B2`, `=SUM(D2:D2)B2`)
   - top-level (outside any function) comma/separator (`=SUM(D2:D2), B2`)
   - Excel's space-intersection operator between two operands (`=SUM(D2 D2)`)
   - unbalanced/misordered parens beyond the earlier plain paren-count check
   - requires the formula to start with a function-open token and end on a completed value
   - still explicitly allows the previously-supported shapes: function-result arithmetic (`=SUM(D2:D2)*2`) and multiple range arguments in one call (`=SUM(D2:D2,C2:C2)`)
3. Corresponding new tests added to `tests_xlsx_style_patcher.py` (1 new: out-of-bounds range) and `tests_xlsx_format_formula_patcher.py` (7 new: out-of-bounds range, out-of-bounds target cell, function-result arithmetic allowed, multi-range arguments allowed, trailing/adjacent/top-level-comma/space-intersection rejections).

Manual spot-check (`_validate_xlsx_formula`, run inside the worktree venv) confirms:
  - valid whitelist formulas still pass: `=SUM(D2:D2)`, `=AVERAGE(D2:D2)`, `=IF(COUNT(D2:D2)>0,SUM(D2:D2),0)`, `=SUM(D2:D2)*2`, `=SUM(D2:D2,C2:C2)` → all `None` (no error)
  - malformed/adjacent/intersection cases correctly rejected: `=SUM(D2:D2) B2`, `=SUM(D2:D2)B2`, `=SUM(D2:D2), B2`, `=SUM(D2 D2)` → all return a specific failure reason

## Excluded (per instructions, untouched)

XLSX row/column insert or merge, DOCX/HWP/PPTX style work, PDF structure modification, regenerate/templates.

## Tests run (exact commands, from worktree root unless noted)

Backend (venv: `backend/.venv/bin/python`, settings: `config.settings_test`):

```
cd backend
DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents.tests_pdf_patcher.PdfRedactOverlayTest -v 2
# → 3 passed (confirms PDF CJK stabilization already in place)

DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents.tests_xlsx_style_patcher apps.documents.tests_xlsx_format_formula_patcher apps.documents.tests_e2e_xlsx_loop apps.documents.tests_pdf_patcher -v 1
# → 86 passed, 0 failed (focused XLSX + PDF suite, current state)

DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents.tests_xlsx_format_formula_patcher -v 0
# → 44 passed, 0 failed (set_number_format + set_formula unit/integration, including the new hardening tests)

DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents -v 0
# → full apps.documents suite: 219 passed, 0 failed (current, post-hardening count)
```

Frontend (from `frontend/`):

```
npx vitest run tests/ChangeSuggestionCard.test.jsx
# → 13 passed (5 pre-existing set_cell_style tests + 8 set_number_format/set_formula summary tests)

npx vitest run
# → 14 files / 86 tests passed, 1 file failed to load (tests/PdfViewer.test.jsx — see Risks below, unrelated to this diff)
```

## Remaining risks / notes for reviewer

- **`tests/PdfViewer.test.jsx` fails to load, pre-existing and out of my scope.** Error: `Denied ID /Users/haram/Desktop/office-ax/frontend/node_modules/@rhwp/core/rhwp_bg.wasm?url` — Vite/vitest resolves a wasm asset import to the **sibling main-repo path** (`/Users/haram/Desktop/office-ax/frontend/...`) instead of this worktree's `node_modules`, and the sandbox denies that path. I did not touch `PdfViewer.jsx`/`PdfViewer.test.jsx`/anything HWP-related, and `git status` confirms neither file is modified in this worktree. This looks like a worktree/sandbox path-resolution issue (possibly a symlinked or hoisted `@rhwp/core` dependency), not a regression from this work. Flagging for orchestrator — may need a permission/allowlist adjustment for the sibling repo path, or a worktree-local `node_modules` reinstall, neither of which I attempted since both are outside the "no main repo edits" boundary and outside this task's scope.
- Formula validation is intentionally conservative (regex/whitelist based, not a full parser). It blocks `!`, `[`, `]`, `'`, `@`, `&` at the charset level (blocks cross-sheet/external refs, string concat, implicit intersection) and requires at least one whitelisted top-level/nested function call. Bare arithmetic (`=D2+D2`) is rejected by design per roadmap Phase 3 ("허용 함수 whitelist 사용") — flagging in case product wants bare arithmetic allowed later.
- `set_formula`'s `expected_context` is validated against the whole sheet (not bounded to the target cell), since the target cell is normally empty before the formula is written — bounding it to the anchor cell would make `non_empty_cells` unsatisfiable in the common "fill in an empty total cell" case. This is a deliberate design choice, documented in code comments and `docs/patch_plan_schema.md`.
- The tokenizer-based validator (`_validate_xlsx_formula_tokens`) is a second, stricter pass layered on top of the original regex/charset/whitelist pass — both must pass. It depends on `openpyxl.formula.tokenizer.Tokenizer`, which is a private-ish internal API (not part of openpyxl's documented public surface); if a future openpyxl upgrade changes its token types/subtypes (`OPERAND`, `FUNC`/`OPEN`/`CLOSE`, `PAREN`, `SEP`, `OPERATOR-INFIX`), this function would need re-verification. Current pinned openpyxl in this venv exercises it correctly (all 44 focused tests pass).
- No permission prompts were triggered during this session (venv path and settings module were provided up front by the user).

## Status

All 8 originally-planned tasks complete, plus this hardening pass now verified and owned. Current counts: backend `apps.documents` = 219 passed, focused XLSX format/formula suite = 44 passed, frontend `ChangeSuggestionCard` = 13 passed. No uncommitted regressions found. **Ready for commit** (not merged/pushed — awaiting explicit instruction per merge policy).
