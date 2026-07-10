# AGENT_PLAN.md

## Scope

Implement only the beta-before items from `docs/product/architecture/document-edit-execution-layer-design-v1-ko.md` section 10.1:

- DOCX `replace_text` with 2+ matches must stop as `NEEDS_CONFIRMATION`.
- PDF structural render validation smoke check covers only invariant 7.1 items 1-2.
- Clean up stable failure reason codes around patch artifact generation.
- Keep T2, structural table/field edits, and vision/image fallback out of scope.

## Likely Files

- `backend/apps/documents/patcher.py`
- `backend/apps/documents/tasks.py`
- `backend/apps/documents/tests_patcher_pure.py`
- `backend/apps/documents/tests_docx_pptx_patcher.py`
- `backend/apps/documents/tests_pdf_patcher.py`
- Possibly `backend/apps/documents/tests_usage_event.py`

## Implementation Steps

1. Add stable patch failure-code constants, at least `ambiguous_anchor` and `render_validation_failed`, while keeping existing human-readable messages.
2. Update `render_docx` to count all paragraph-level `text_match` occurrences before mutating:
   - 0 matches: keep existing failed behavior.
   - 1 match: apply the existing replacement behavior.
   - 2+ matches: append `needs_confirmation_items` with code `ambiguous_anchor`, produce no mutation for that change.
3. Reuse existing `PatchResult.needs_confirmation_items` and `persist_patch_result()` status handling; do not add a DOCX resolver abstraction.
4. Add PDF post-render validation before returning successful bytes:
   - Modified PDF opens/renders without exception.
   - Page count is unchanged and pages are not unexpectedly empty.
   - For text replacement/redact-overlay changes, `replacement` is extractable near the resolved rect and `original` is gone from that local area.
   - Validation failure returns no READY artifact and marks affected changes with `render_validation_failed`.
5. Wire failure codes into patch usage-event metadata if `tasks.py` records failed artifact generation.

## Tests

Focused command:

```bash
cd backend
python manage.py test apps.documents.tests_patcher_pure apps.documents.tests_docx_pptx_patcher apps.documents.tests_pdf_patcher --settings=config.settings_test
```

Add or update tests for:

- DOCX single match still succeeds and writes replacement.
- DOCX no match still fails.
- DOCX duplicate `text_match` produces `DocumentChange.Status.NEEDS_CONFIRMATION`, `DocumentVersion.Status.NEEDS_CONFIRMATION`, no artifact, and `needs_confirmation_change_ids`.
- Mixed DOCX resolved + ambiguous changes preserve partial success semantics.
- PDF readable `replace_text` happy path still passes.
- PDF validation failure produces code `render_validation_failed` and no READY artifact.
- Usage-event metadata includes failure code if reason-code cleanup touches `tasks.py`.

Broader backend check after focused tests:

```bash
cd backend
python manage.py test apps.documents --settings=config.settings_test
```

Prefer Docker final validation if available:

```bash
docker compose run --rm backend python manage.py test apps.documents --settings=config.settings_test
```

## Out Of Scope

- T2 operations, table/cell structural editing, row/column insertion.
- Vision/crop/image fallback or PII image policy work.
- Pixel diff, PDF invariant 7.1 items 3-4, DOCX/HWP render validation.
- Frontend changes unless backend response shape unexpectedly changes.
- Product-doc edits unless separately assigned.
