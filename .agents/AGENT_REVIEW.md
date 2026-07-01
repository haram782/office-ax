# Agent Review

## Scope

Reviewed the `next-roadmap-xlsx-ops` diff for the roadmap v1 bundle:

- XLSX `set_number_format`
- XLSX `set_formula`
- schema/prompt/persistence updates
- frontend `ChangeSuggestionCard` summaries
- XLSX E2E sales scenario
- PDF CJK `redact_overlay` regression confirmation

Files reviewed: `backend/apps/documents/patcher.py`, `tasks.py`, `views.py`,
`tests_xlsx_format_formula_patcher.py`, `tests_xlsx_style_patcher.py`,
`tests_e2e_xlsx_loop.py`, `frontend/src/pages/Workspace/ChangeSuggestionCard.jsx`,
`frontend/tests/ChangeSuggestionCard.test.jsx`, `docs/patch_plan_schema.md`,
`docs/product/patch-plan-schema-v0-ko.md`.

## Findings

### Resolved: malformed `set_formula` strings with trailing/adjacent tokens

Initial review found that `_validate_xlsx_formula` accepted malformed formulas such as:

- `=SUM(A1:A2) A1`
- `=SUM(A1:A2)A1`
- `=SUM(A1:A2), A1`
- `=SUM(A1 A2)`

This was blocking because those strings could be written directly into the workbook.

Resolution verified:

- Added `_validate_xlsx_formula_tokens` using `openpyxl.formula.tokenizer.Tokenizer`.
- Rejects trailing/adjacent value tokens, top-level commas, malformed ranges, and whitespace intersection references.
- Keeps valid whitelist formulas working, including:
  - `=SUM(D2:D2)*2`
  - `=SUM(D2:D2,C2:C2)`
  - `=IF(COUNT(D2:D2)>0,SUM(D2:D2),0)`
- Added regression tests for accepted and rejected shapes.

### No Remaining Blocking Findings

No merge-blocking issues remain after the formula-token fix.

## Non-Blocking Notes

- `set_formula.expected_context` is intentionally validated against the whole sheet rather than the target cell, because the target formula cell is often empty before patching.
- Bare arithmetic such as `=D2+D2` remains rejected by design because the roadmap requires whitelist function use.
- `frontend/tests/PdfViewer.test.jsx` still has an out-of-scope worktree/node_modules wasm path issue. The touched frontend test `ChangeSuggestionCard.test.jsx` passes.
- Additional XLSX bounds hardening for `XFE1`/out-of-range coordinates is appropriate and covered for style, number format, and formula paths.

## Verification

- `DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents.tests_xlsx_format_formula_patcher -v 1` -> 44 tests passed.
- `DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents -v 1` -> 219 tests passed.
- `npm test -- tests/ChangeSuggestionCard.test.jsx` -> 13 tests passed.

## Merge Readiness

Merge-ready from review perspective.
