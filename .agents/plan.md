# Orchestrator Plan

## Workflow

Standard Mode.

Stages:

1. Planning
2. Implementation
3. Test
4. Review
5. Validation
6. Commit
7. Merge gate

## Initial Implementation Notes

- Reuse the existing XLSX style validation structure from `backend/apps/documents/patcher.py`.
- Treat predictable validation failures as `PatchResult.failed_items`.
- Keep `expected_context` mandatory for new XLSX operations.
- Add operation-specific frontend summaries rather than empty diff rows.
- Keep work inside `/Users/haram/Desktop/office-ax-worktrees/next-roadmap-xlsx-ops`.

## Planner Implementation Split

Recommended order:

1. PDF CJK stabilization first.
   - Confirm `backend/apps/documents/tests_pdf_patcher.py::PdfRedactOverlayTest::test_redact_overlay_cjk_replacement_is_not_garbled`.
   - Fix only `redact_overlay` font insertion if the test fails; keep PDF structure modification out of scope.

2. XLSX operation backend core.
   - Extend the existing `set_cell_style` pattern in `backend/apps/documents/patcher.py`.
   - Add shared XLSX range/context helpers only if they reduce duplication across `set_cell_style`, `set_number_format`, and `set_formula`.
   - Implement `set_number_format` with `anchor.type=cell_range`, required `patch.expected_context`, required whitelisted `patch.number_format`, and the existing max range limit.
   - Implement `set_formula` for a single cell only, with required context and formula validation before assignment.

3. Schema, prompt, and persistence contract.
   - Update PatchPlan docs/schema text for `set_number_format` and `set_formula`.
   - Update `_PATCH_PLAN_SYSTEM_PROMPT` in `backend/apps/documents/views.py`.
   - Normalize top-level `expected_context` into `patch.expected_context` for all XLSX format operations, not only `set_cell_style`.
   - Keep predictable validation failures as `PatchResult.failed_items`.

4. Frontend summaries.
   - Extend `frontend/src/pages/Workspace/ChangeSuggestionCard.jsx` so `set_number_format` and `set_formula` render operation summaries, not empty original/replacement diff rows.
   - Reuse existing `anchorLabel` and summary style; avoid new card-level UI patterns.

5. XLSX E2E scenario.
   - Add or extend E2E coverage in `backend/apps/documents/tests_e2e_xlsx_loop.py` after unit/integration tests pass.
   - Cover one artifact with `set_cell_style`, `set_number_format`, and `set_formula`, plus partial failure behavior.

Likely files touched:

- `backend/apps/documents/patcher.py`
- `backend/apps/documents/views.py`
- `backend/apps/documents/tests_pdf_patcher.py` if regression needs adjustment or stronger assertion
- `backend/apps/documents/tests_xlsx_style_patcher.py` or new focused XLSX operation tests
- `backend/apps/documents/tests_e2e_xlsx_loop.py`
- `frontend/src/pages/Workspace/ChangeSuggestionCard.jsx`
- `frontend/tests/ChangeSuggestionCard.test.jsx`
- `docs/patch_plan_schema.md`
- Possibly `docs/product/patch-plan-schema-v0-ko.md` if product contract docs must stay synchronized

Test matrix:

- Backend PDF: CJK `redact_overlay` replacement text is extractable and not Helvetica-garbled; existing PDF annotate/redact tests still pass.
- Backend XLSX number format happy path: allowed formats apply to a range and values remain unchanged.
- Backend XLSX number format boundary/failure: missing context, bad range, oversized range, wrong sample value, blank required cell, unknown patch key, and unlisted number format all fail as individual changes.
- Backend XLSX formula happy path: allowed formula is stored in a single target cell and readable with `openpyxl(data_only=False)`.
- Backend XLSX formula boundary/failure: range target rejected, missing context rejected, external refs/URLs/macros/forbidden functions/unknown functions rejected, malformed formula rejected.
- Backend integration: mixed `replace_cell` + style + number format + formula applies successful changes and marks only invalid changes failed.
- Frontend: `ChangeSuggestionCard` shows summaries for style, number format, and formula operations; ordinary text/cell diffs remain unchanged.
- E2E: upload/original version/draft changes/apply/patch artifact/download/openpyxl verification for the sales-table workflow; partial failure preserves successful operations.

Risks and blockers:

- Formula validation is the highest-risk backend item. Use a conservative parser/regex whitelist and explicitly reject external workbook refs, URLs, volatile/web functions, and unknown functions before assignment.
- `expected_context` helper extraction can accidentally change existing `set_cell_style` behavior. Preserve current error messages where tests depend on them unless updating tests deliberately.
- Operation ordering matters when `replace_cell` and context-checked operations touch the same cells. E2E fixtures should avoid context cells mutated earlier, or define ordering expectations explicitly.
- PDF CJK may depend on installed PyMuPDF font support. If `korea-s` is unavailable in the runtime, implementer must find a supported built-in CJK font path/name without adding global font assumptions.
- Prompt changes can over-generate operations. Tests should verify ambiguous requests return no operation or fail validation predictably.

Staffing recommendation:

- One implementer is enough for this bundle if done in the order above. Backend dominates the work; frontend changes are narrow.
- Backend/frontend split is optional only if schedule pressure matters. If split, backend should finish operation contract and example payloads before frontend starts.
