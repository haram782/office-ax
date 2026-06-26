# Office-AX Viewer-First Workflow Automation v0

## 1. Product Direction

Office-AX starts as an AI document editing workspace, but its deeper product goal is to infer the user's repeated document workflow and convert it into automation.

The first user-facing value is not "build a pipeline." The first value is:

- upload a document
- inspect it in a viewer
- ask AI to review or revise it
- see suggested changes on the document
- apply, reject, or download the result

The long-term value is:

- observe the user's document work
- infer repeated flows across input documents, references, operations, outputs, and delivery
- suggest automation only when it reduces future work
- let advanced users refine the inferred flow in a pipeline editor

## 2. Positioning

Office-AX should replace the common workflow where users upload or paste documents into GPT, Gemini, or Claude, then manually copy the answer back into a file.

The product should feel better than a general LLM web chat because it keeps the document, the AI response, the proposed edits, and the final output in one workspace.

Positioning statement:

> AI document work should happen on the document, not beside it.

Korean product language:

> GPT로 복붙하던 문서 수정, 이제 문서 위에서 확인하고 적용하세요.

## 3. Core Product Thesis

The product should not ask users to design automation first.

Users should work normally:

1. Upload a document.
2. Ask for review, correction, formatting, comparison, or generation.
3. Accept or reject useful suggestions.
4. Download or reuse the result.

Office-AX should quietly learn from those actions.

Automation order:

1. C: infer repeated document workflows.
2. B: offer to save the inferred workflow as a reusable rule.
3. A: expose the rule as an editable pipeline for advanced configuration.

This means the pipeline editor is not the primary entry point. It is the place where inferred work becomes explicit and configurable.

## 4. First User Delight

The first "wow" moment should be document editing in the viewer:

- AI finds the relevant part of the document.
- The location is highlighted.
- The user sees original text and suggested replacement.
- The user can apply or reject the suggestion.
- The final document feels produced, not merely described.

The first delight is emotional and visual: the document appears to be worked on directly.

The deeper retention comes later: Office-AX notices repeated flows and offers automation.

## 5. Initial Format Strategy

Prioritize HWP and XLSX.

### HWP

HWP is important for the Korean business document market.

Initial scope:

- extract document text and structure
- identify paragraphs or text anchors
- generate review and edit suggestions
- highlight approximate text or paragraph locations
- support document-style tasks such as official tone, missing fields, risk review, and form alignment

Later scope:

- precise HWP patching
- stronger layout-aware anchoring
- template-aware generation

### XLSX

XLSX is good for proving precise document-level AI work.

Initial scope:

- cell-level extraction
- cell address based highlights
- formula, amount, date, missing value, and consistency checks
- suggested replacement values

XLSX should be used as an early spike for structured edit suggestion UX because cell addresses make location and apply behavior easier to validate.

## 6. AI Capability Scope

Office-AX must support the work users already do in general LLM tools:

- summarize
- correct typos
- improve tone
- convert to official/business style
- review document risks
- detect missing fields
- find contradictions
- mask personal information
- align to a company form
- draft a reply, report, notice, or official document

The differentiator is not that these tasks exist. The differentiator is that Office-AX turns them into document-native work:

- location-aware suggestions
- before/after comparison
- apply/reject controls
- saved rules
- inferred workflows

## 7. Workflow Inference Model

Office-AX should infer document workflows, not just repeated prompts.

The target pattern is:

```text
Input -> Reference -> Operation -> Output -> Delivery
```

Examples:

```text
청약신청서.hwp
-> 청약 자격 기준표.xlsx
-> 신청자 정보 추출, 조건 비교, 누락/리스크 검토
-> 검토 결과 요약서
-> 담당자에게 전달
```

```text
견적서.xlsx
-> 회사 가격 정책표.xlsx
-> 금액/수식/날짜 오류 검토
-> 수정 제안 또는 정정본
-> 최종 파일 다운로드
```

The automation target is a document workflow. A single action such as "공문체로 바꿔줘" is an operation inside a workflow, not a full pipeline.

## 8. Product Layers

### 1. Viewer Workspace

The normal work surface.

Responsibilities:

- upload and open documents
- preview document content
- chat with AI
- show suggestions and highlights
- let users apply, reject, or download results

### 2. Activity Capture

The background event layer.

Responsibilities:

- capture user actions without interrupting work
- record document roles, prompts, references, outputs, and accepted changes
- preserve enough evidence for later workflow inference

### 3. Workflow Inference

The intelligence layer.

Responsibilities:

- group events into task runs
- detect repeated document workflow patterns
- infer input, reference, operation, output, and delivery steps
- score whether a pattern is worth suggesting

### 4. Automation Suggestion

The user-facing bridge.

Responsibilities:

- suggest automation only when it reduces work
- avoid exposing internal inference details
- let the user save, dismiss, or refine the suggestion

### 5. Pipeline Editor

The advanced editor.

Responsibilities:

- convert an automation candidate into a pipeline draft
- let users edit missing steps, triggers, references, outputs, and delivery
- support future email, schedule, RAG, and external delivery channels

### 6. Execution Engine

The future automation runtime.

Responsibilities:

- execute confirmed pipelines
- track run history
- handle failures, retries, and notifications

## 9. UX Principle: Do Not Over-Explain Inference

Users come to Office-AX to work, not to inspect the system's reasoning.

Office-AX should infer in the background and speak only when useful.

Do not show:

- "Input -> Reference -> Operation -> Output -> Delivery"
- "confidence: 0.78"
- "intent: compare"
- "document_role: reference"

Show:

- "이 검토 방식, 다음에도 자동으로 적용할까요?"
- "비슷한 문서가 올라오면 먼저 확인해둘게요."
- "이 작업을 저장하면 다음부터 검토 시간을 줄일 수 있어요."

Principle:

> Office-AX does not explain the user's workflow. It quietly understands the workflow and offers the next useful action.

## 10. Automation Suggestion Surfaces

Use three surfaces:

### Workspace Quiet Card

Small and non-blocking.

Example:

```text
자동화 후보 2개 발견
- 청약신청서 검토
- 견적서 오류 확인
```

### Dashboard Analysis

More analytical.

Example:

```text
이번 주 반복 업무
1. 청약신청서 검토 - 5회 반복
2. 견적서 금액 오류 확인 - 4회 반복
```

### Chat Suggestion

Natural and short.

Example:

```text
이 방식은 다음 청약서에도 그대로 쓸 수 있어요.
저장해둘까요?
```

Avoid blocking modal prompts during active editing.

## 11. Minimum Event Vocabulary

MVP activity events:

- document_uploaded
- document_opened
- reference_selected
- prompt_submitted
- llm_response_generated
- edit_suggestion_generated
- edit_suggestion_applied
- edit_suggestion_rejected
- output_generated
- file_downloaded
- message_copied
- automation_suggestion_shown
- automation_suggestion_accepted
- automation_suggestion_dismissed

Common fields:

- user
- session
- document_id
- file_type
- document_fingerprint
- event_type
- timestamp
- payload

Important payload concepts:

- document_role: input, reference, output
- intent: extract, compare, validate, rewrite, format, generate, send
- change_types: date_format, pii_masking, missing_field, tone, amount_check, legal_risk
- artifact: source_doc, reference_doc, generated_doc, final_download

## 12. Initial Data Concepts

These are planning concepts, not final implementation names.

### DocumentObject

Represents a document used in work.

Roles:

- input
- reference
- output

### TaskRun

Represents one user work session or meaningful document task.

Examples:

- review one HWP application form
- compare one spreadsheet with a policy table
- generate a report from uploaded materials

### TaskStep

Represents an inferred step inside a task.

Types:

- extract
- compare
- validate
- rewrite
- format
- generate
- send

### WorkflowCandidate

Represents an inferred repeated workflow.

Fields to consider:

- title
- user
- observed_steps
- evidence_events
- repeated_count
- confidence
- missing_context_questions
- status: suggested, accepted, dismissed, converted_to_pipeline

### PipelineDraft

Represents a user-confirmed or editable version of a workflow candidate.

This can later become a full Pipeline.

## 13. Missing External Context

Some steps happen outside the current workspace:

- receiving files by email
- forwarding results to another person
- uploading to a shared folder
- entering data into ERP or groupware
- requesting approval

Do not pretend these steps are known.

When a workflow candidate is shown, ask lightweight completion questions:

```text
검토 결과는 보통 어디로 전달하나요?
[다운로드만] [이메일로 발송] [담당자에게 전달] [공유폴더 저장] [직접 입력]
```

These questions should appear during automation refinement, not during active document editing.

## 14. MVP Recommendation

Build toward this sequence:

### Phase 1: Edit Suggestion Schema

Define a structured LLM output format that the viewer can render.

Required fields:

- summary
- detected issues
- edit suggestions
- target text or cell address
- replacement
- reason
- confidence
- change type
- anchor hint

### Phase 2: XLSX Spike

Validate precise location and apply UX.

Scope:

- cell-level issue detection
- highlighted cells
- suggested replacements
- apply/reject

### Phase 3: HWP Workspace

Validate Korean document editing value.

Scope:

- paragraph or text-anchor highlights
- review suggestions
- official tone and form alignment
- risk and missing field detection

### Phase 4: Activity Capture

Start logging task-level events from the workspace.

Scope:

- uploads
- prompts
- references
- generated suggestions
- applied/rejected suggestions
- downloads

### Phase 5: Workflow Candidate v0

Use simple rules before complex ML.

Example rule:

```text
Within 7 days,
same user,
similar document type,
similar reference use,
similar operation types,
3 or more task runs,
and meaningful apply/download behavior
=> create workflow candidate.
```

### Phase 6: Pipeline Draft

Convert accepted candidates into editable pipeline drafts.

The pipeline editor should receive inferred steps, not start from a blank canvas.

## 15. Open Questions

1. What is the first demo document?
   - HWP application form
   - XLSX quotation or settlement sheet
   - another Korean business document

2. Which HWP open-source library is the implementation baseline?

3. What level of HWP patching is realistic for v0?
   - text extraction only
   - approximate highlight
   - generated revised document
   - real in-place patch

4. What should count as "successful work"?
   - suggestion applied
   - file downloaded
   - message copied
   - user sends follow-up approval

5. How should RAG/reference selection be represented?
   - style reference
   - policy/reference document
   - output template
   - prior example

6. When should an automation candidate be shown?
   - after download
   - after repeated prompt
   - in dashboard only
   - as a quiet workspace card

## 16. Next Planning Documents

Recommended follow-up docs:

1. `document-edit-suggestion-schema-v0.md`
2. `document-workflow-inference-v0.md`
3. `hwp-xlsx-viewer-mvp-v0.md`
4. `automation-candidate-to-pipeline-v0.md`

