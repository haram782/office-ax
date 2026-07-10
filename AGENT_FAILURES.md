# Agent Failure Patterns

## Claude Worker Bootstrap Bypass Prompt

- Symptom: Claude implementer/tester sessions spawned successfully but stopped at the interactive "Bypass Permissions mode" confirmation before role handoff.
- Root cause: The launcher starts Claude in a mode that requires a broad interactive acceptance prompt, which the orchestrator should not auto-approve as a worktree-scoped permission.
- Prevention: Prefer a non-interactive, worktree-scoped Claude startup mode or route the worker to Codex when the prompt appears.
- Harness action: Review `spawn-agent-session.sh` Claude provider defaults before relying on Claude workers for unattended first-run automation.
- Evidence: 2026-07-10 first run for `document-edit-execution-layer`; Claude surfaces were exited with the default "No, exit" and replaced by Codex implementer/tester.
- Status: Open
