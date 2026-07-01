# Agent Validation

## v1 XLSX `set_cell_style` — Final Validation

Scope: `docs/product/document-format-editing-ax-v1-ko.md` v1 POC, worktree
`/Users/haram/Desktop/office-ax-worktrees/v1-xlsx-style-poc` (branch `work/v1-xlsx-style-poc`).

### Review findings (AGENT_REVIEW.md) — resolution check

1. `expected_context` not required → **RESOLVED**. `_validate_xlsx_style_expected_context`
   in `backend/apps/documents/patcher.py` now rejects missing/empty `expected_context`
   before any style is applied (`validate_xlsx_style_change` calls it unconditionally).
2. `expected_context` refs unvalidated/unconstrained → **RESOLVED**.
   `_validate_xlsx_style_context_cell_ref` parses each ref via `openpyxl.utils.cell.coordinate_to_tuple`
   (invalid syntax → failure) and checks it falls inside `anchor.range` bounds
   (`min_row/max_row/min_col/max_col`).
3. `_PATCH_PLAN_SYSTEM_PROMPT` inconsistent → **RESOLVED**. `backend/apps/documents/views.py:800`
   now lists `set_cell_style` in "Allowed operations" and includes a full `set_cell_style` rules
   section (range size cap, expected_context requirement, patch whitelist).
4. Validation exceptions not converted to `failed_items` → **RESOLVED**. `render_xlsx` wraps
   both `validate_xlsx_style_change` and `apply_xlsx_cell_style` calls in `try/except Exception`,
   appending to `failed_items` instead of propagating. This is an acceptable use of try/except
   per `rules/design.md` (external/library boundary — openpyxl parsing) rather than a Result type,
   since the caller-facing contract of `render_xlsx` is already "collect failures into `failed_items`".
5. Required new tests (missing context / invalid refs / refs outside range) → **RESOLVED**.
   `backend/apps/documents/tests_xlsx_style_patcher.py` includes
   `test_missing_expected_context_fails`, `test_empty_expected_context_fails`,
   `test_invalid_context_ref_range_syntax_fails`, `test_invalid_context_ref_garbage_fails`,
   `test_context_ref_outside_range_fails`, `test_non_empty_cells_ref_outside_range_fails`,
   plus whitelist/oversized-range/missing-sheet/value-mismatch coverage.

Non-blocking note from review (style overwrite of unrelated attributes) — still present by
design in `apply_xlsx_cell_style` (rebuilds Font/Alignment/Border only for touched sub-fields,
preserves the rest via `cell.font.name` etc. carry-over). Acceptable for POC scope as reviewer
noted; no further action required.

### Test re-verification (independently re-run, not just trusting tester report)

- `apps.documents.tests_xlsx_style_patcher` + `apps.documents` (full app suite):
  173/173 passed, confirmed by direct re-run in the worktree.
- `frontend/tests/test_changeSuggestions.mjs`: 46/46 passed, confirmed by direct re-run.
- `frontend/tests/ChangeSuggestionCard.test.jsx` (vitest): 7/7 passed, confirmed by direct re-run.
- `PdfViewer.test.jsx` collection failure: confirmed pre-existing/environment-only —
  `git diff --name-only` for this worktree touches no PDF/WASM/rhwp-related files, so the
  failure is not attributable to this change. Accepted as tester assessed.

### Requirement coverage

- Backend: `set_cell_style` operation implemented in `patcher.py` (validate → apply →
  failed_items on any failure), wired through `render_xlsx`.
- Prompt: `_PATCH_PLAN_SYSTEM_PROMPT` and `tasks.py` allowed-operations map both updated for
  `excel` → `["replace_cell", "set_cell_style"]`.
- Persistence: `GeneratePatchPlanView` merges `expected_context` into `patch` on `DocumentChange`
  creation and returns `patch` in the API response.
- Frontend: `ChangeSuggestionCard` renders a style-summary line instead of an original→replacement
  diff when `operation === 'set_cell_style'`; `changeSuggestions.js` preserves `operation`/`patch`
  and dedupes `cell_range` anchors by exact sheet+range match (overlap detection explicitly out of
  v1 scope per code comment — acceptable).
- Docs: `docs/patch_plan_schema.md` and `docs/product/patch-plan-schema-v0-ko.md` both updated with
  `cell_range` anchor spec and `set_cell_style` payload example, consistent with the implementation.

### Merge readiness

- Worktree is on `work/v1-xlsx-style-poc`, changes present but **uncommitted** (`patcher.py`,
  `tasks.py`, `views.py`, docs, frontend files modified; `tests_xlsx_style_patcher.py` and
  `ChangeSuggestionCard.test.jsx` untracked). Per `rules/merge.md` "Commit Before Merge Rule",
  these must be committed on the worktree branch before merge — this is the only remaining gap.
- All review-blocking findings resolved and verified against the actual diff (not just report text).
- All required/focused tests independently re-run and green.
- Non-blocking PdfViewer failure confirmed unrelated to touched files.

**Validation result: PASS, pending commit.** No blocking issues remain in the implementation.
Recommend orchestrator direct commit of the worktree changes (new files included) before merge.
