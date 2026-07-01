# Agent Validation

## Scope

`document-editing-ax-next-roadmap-v1-ko.md` Phase 1–5 bundle (PDF CJK stabilization,
XLSX `set_number_format`, XLSX `set_formula`, schema/prompt/persistence, frontend
summaries, XLSX sales-scenario E2E), worktree
`/Users/haram/Desktop/office-ax-worktrees/next-roadmap-xlsx-ops` (`work/next-roadmap-xlsx-ops`).

Note: root-level `AGENT_REVIEW.md` / `AGENT_TEST_REPORT.md` / `AGENT_VALIDATION.md` are
stale artifacts already committed on `main` from the prior, separately-merged
`v1-xlsx-style-poc` task (`bc762a7`). They describe `set_cell_style` only and are unrelated
to this bundle. This validation covers the artifacts in `.agents/` (`plan.md`,
`AGENT_TEST_REPORT.md`, `AGENT_REVIEW.md`) for the current diff.

## Requirement coverage (roadmap §6, Phase 1–5)

- **Phase 1 (PDF CJK stabilization)**: `PdfRedactOverlayTest` (3 tests, incl.
  `test_redact_overlay_cjk_replacement_is_not_garbled`) independently re-run → pass.
  Fix (`fontname="korea-s"`) was already present on the branch; no additional change
  needed, consistent with implementer's report.
- **Phase 2 (`set_number_format`)**: `anchor.type=cell_range`, mandatory
  `expected_context`, `number_format` whitelist (7 formats from roadmap §6.Phase2),
  200-cell range cap reused from `set_cell_style` — verified in
  `patcher.py:454-505`. Confirmed cell values are untouched by `apply_xlsx_number_format`
  (only `cell.number_format` is set).
- **Phase 3 (`set_formula`)**: single-cell only (`anchor.type=cell`, `cell_range`
  rejected — `patcher.py:522-524`), function whitelist `SUM/AVERAGE/COUNT/COUNTA/MIN/MAX/IF`
  with nesting, explicit rejection of external refs/URLs/`INDIRECT`/`HYPERLINK`/
  `WEBSERVICE`/unknown functions — verified in `patcher.py:559-608`, plus a second
  token-level pass (`_validate_xlsx_formula_tokens`, `patcher.py:611-702`) using
  `openpyxl.formula.tokenizer.Tokenizer` that closes the trailing/adjacent-token gap
  the reviewer originally flagged (`=SUM(A1:A2) A1` style strings). Both regex and
  tokenizer layers are covered by dedicated tests.
- **Phase 4 (prompt/schema)**: `_PATCH_PLAN_SYSTEM_PROMPT` in `views.py` lists both new
  operations with explicit anchor shape, whitelist values, and forbidden patterns; adds
  an explicit "if unsure, omit the operation" rule matching roadmap §6.Phase4 prompt
  principles. `_XLSX_FORMAT_OPERATIONS` generalizes `expected_context` merging from
  `set_cell_style`-only to all three XLSX format operations
  (`views.py:992-1002`) — dispatch via set membership, not branching.
  `docs/patch_plan_schema.md` and the Korean product doc are updated consistently with
  the implementation (spot-checked against `patcher.py` whitelists — values match).
- **Phase 5 (E2E sales scenario)**: `XlsxE2ESalesScenarioTest` in
  `tests_e2e_xlsx_loop.py:561` implements the exact roadmap scenario (header style →
  number format → formula → download) plus one intentionally-invalid
  `set_number_format` op to verify partial-failure isolation. Confirmed via direct
  read of the test and independent re-run (see below).

Error handling: all predictable validation failures return a reason string
(`Result`-shaped, not exceptions) from `validate_xlsx_*_change`; `render_xlsx` is the
only place that wraps calls in `try/except Exception`, and only to convert unexpected
library-boundary failures into `failed_items` — consistent with `rules/design.md`
(Result for business rules, try/except at infra/library boundaries), same pattern as
the already-approved `set_cell_style` code.

## Review findings (AGENT_REVIEW.md) — resolution check

- Malformed `set_formula` strings with trailing/adjacent tokens (`=SUM(A1:A2) A1`,
  `=SUM(A1:A2)A1`, `=SUM(A1:A2), A1`, `=SUM(A1 A2)`) → **RESOLVED**, confirmed by reading
  `_validate_xlsx_formula_tokens` and the corresponding rejection tests in
  `tests_xlsx_format_formula_patcher.py`.
- No other blocking findings recorded; non-blocking notes (expected_context validated
  against whole sheet for `set_formula`, bare-arithmetic rejection by design,
  pre-existing `PdfViewer.test.jsx` worktree/wasm path issue) are documented in code
  comments and/or the test report, not silently dropped.

## Test re-verification (independently re-run in this session, not just trusting reports)

- Backend: `DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py test apps.documents -v 0`
  → **219 passed, 0 failed** (matches reviewer's count).
- Backend: `PdfRedactOverlayTest -v 2` → **3 passed**, including the CJK regression test.
- Frontend: `npx vitest run tests/ChangeSuggestionCard.test.jsx` → **13 passed**.
- `PdfViewer.test.jsx` collection failure reconfirmed as pre-existing/out-of-scope: no
  PDF/WASM/`@rhwp`-related file is touched by this diff (`git diff --stat` above), and the
  failure is a worktree `node_modules` path-resolution issue (denied path resolves to the
  sibling main-repo checkout), not a code regression.

## Edge cases confirmed covered (by reading `tests_xlsx_format_formula_patcher.py` scope)

- missing/empty `expected_context`, range outside bounds, oversized range, unknown sheet
- unlisted `number_format`, unknown patch keys
- `set_formula` on `cell_range` anchor (rejected), missing formula, empty formula
- external sheet/workbook refs, URLs, string concat, forbidden/unknown functions,
  unbalanced parens, trailing/adjacent tokens (regex + tokenizer double coverage)
- mixed success/failure in one E2E run (partial failure isolation)

## TDD artifact note

No standalone Red-failure log was retained/handed off for this cycle (only the final
Green run outputs are in `AGENT_TEST_REPORT.md`). Test content itself is substantive
(explicit boundary/failure/regression cases per file, not superficial), and this
follows the same reporting precedent already accepted for the merged `set_cell_style`
POC (`AGENT_VALIDATION.md` on `main` also validated without a retained Red log).
Non-blocking for this bundle; flagging so future cycles retain the Red log explicitly
per `rules/tdd.md`.

## Merge readiness

- All requirement items in roadmap §6 Phase 1–5 are implemented and verified against
  the actual diff (not just report text).
- All review-blocking findings resolved and independently confirmed.
- All required tests independently re-run and green (219 backend + 13 frontend).
- No blocking issues remain. Out-of-scope items (row/column insert, DOCX/HWP/PPTX
  style, PDF structure, regenerate) correctly untouched.

**Validation result: PASS.** Ready for commit/merge gate per `plan.md` "Next Gate".
