# Harness Refresh — Orchestrator Profile Delta

Source read: `~/.codex/profiles/orchestrator.md`, `~/.codex/docs/merge-policy.md`,
`.agents/status.md`. No product files or global harness edited.

## 1. Profile boundary (changed)

Orchestrator now sources from `~/.codex/` (docs: workflow, merge-policy,
validation-policy, output-format, agent-collaboration, agent-automation,
permissions-bootstrap), **not** `~/.claude/profiles/orchestrator.md` or
`~/.claude/rules/*`. Worker profiles (implementer/reviewer/tester/validator) used in
this task so far were `~/.claude/profiles/*` — that is a different root and still
valid for those roles; only the orchestrator role moved.

Default provider routing per `.codex` profile: planner=codex, implementer=claude,
reviewer=codex, tester=claude, validator=claude. Reviewer default provider is now
codex (this task's reviewer ran under claude — note for next routing decision, not
a retroactive problem).

## 2. Commit/merge/push implications (changed — important)

`~/.codex/docs/merge-policy.md` describes **local-merge only**: commit on worktree
branch → merge worktree branch into current branch → delete worktree. It has **no
push/PR/gh step**. This differs from `~/.claude/rules/merge.md`, which this task's
earlier work implicitly assumed (push + `gh pr create` + user-approved `gh pr merge`).

Action: do not push or open a PR under the refreshed orchestrator profile unless the
user explicitly asks for a remote flow. Default path: user approves merge → `git
merge` worktree branch into `main` locally → delete worktree (Worktree Cleanup
Rule). Validator sign-off already obtained (`.agents/AGENT_VALIDATION.md`: PASS) —
orchestrator still must get explicit user merge approval before merging (profile
line 42), regardless of local vs remote path.

## 3. Authoritative agent files

- **Authoritative for this task**: everything under `.agents/` — `plan.md`,
  `AGENT_TEST_REPORT.md`, `AGENT_REVIEW.md`, `AGENT_VALIDATION.md`, `status.md`, this
  file.
- **Not authoritative — stale**: root-level `AGENT_REVIEW.md`, `AGENT_TEST_REPORT.md`,
  `AGENT_VALIDATION.md`. Already-committed leftovers from the prior, separately
  merged `v1-xlsx-style-poc` task (`bc762a7`), describing `set_cell_style` only.
  Do not read, edit, or cite them for this bundle's merge decision.

## 4. Exact relay text for active workers

> Harness note: orchestrator coordination now follows
> `~/.codex/profiles/orchestrator.md` + `~/.codex/docs/merge-policy.md`. Your own
> role profile is unchanged — keep using `~/.claude/profiles/<your-role>.md` and
> writing to `.agents/*.md` as before. One change that affects you: merge will be a
> **local `git merge` into the current branch**, not a pushed PR — do not assume a
> PR will be opened. Treat `.agents/AGENT_REVIEW.md` / `AGENT_TEST_REPORT.md` /
> `AGENT_VALIDATION.md` as the only authoritative artifacts for this task; ignore
> same-named files at the repo root (already-merged, unrelated prior task).

## 5. Open item for orchestrator

Validator already returned PASS. Per refreshed profile: request user's explicit
merge approval next, then perform local merge + worktree deletion — no push step
unless the user asks for one.
