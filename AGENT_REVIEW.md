# Agent Review

## v1 XLSX `set_cell_style` Review

Blocking findings from reviewer:

1. `expected_context` is not required by backend validation. Missing context currently normalizes to `{}` and allows `set_cell_style` to apply without the safety check required by the v1 plan.
2. `expected_context` cell references are not validated or constrained to the target range. Invalid refs may raise exceptions instead of `failed_items`, and refs outside `anchor.range` can make the check pass for the wrong area.
3. `_PATCH_PLAN_SYSTEM_PROMPT` is inconsistent: it still says allowed operations are only `replace_cell`, `replace_text`, and `annotate`, while a later section describes `set_cell_style`.

Non-blocking:

- Style application overwrites some unrelated existing style attributes. Acceptable for the POC if documented, but note the limitation.
- New test files are untracked and must be included in merge.

Required rework:

- Require `expected_context` for `set_cell_style`.
- Validate context refs as A1 cells and require them to be inside `anchor.range`.
- Convert validation exceptions into `failed_items`, not uncaught render failures.
- Add tests for missing expected context, invalid context refs, and context refs outside the styled range.
- Make the prompt allowed-operation section include XLSX `set_cell_style`.

