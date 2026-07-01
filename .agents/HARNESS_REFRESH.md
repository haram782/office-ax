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

## 2. Commit/merge/push implications (superseded — PR flow, no local merge)

Prior guidance in this section described a local-merge-only path per
`~/.codex/docs/merge-policy.md` (commit → local `git merge` into current branch →
delete worktree, no push/PR step). The user has since corrected this: the active
flow for this task is **push + PR, with no local merge and no worktree deletion**.
This matches `~/.claude/rules/merge.md`'s remote path, not the local-only path.

Current state:

- Worktree branch `work/next-roadmap-xlsx-ops` is committed at `98d5006`
  (`feat: add xlsx set_number_format/set_formula ops with hardened validation`).
- **Next gate**: push `work/next-roadmap-xlsx-ops` to `origin`, then open a GitHub
  PR against `main` via `gh pr create`. Do **not** run `git merge` into any local
  branch and do **not** delete this worktree — it stays live for tracking until the
  PR is merged (remotely) and the user explicitly asks for cleanup.
- Validator sign-off already obtained (`.agents/AGENT_VALIDATION.md`: PASS).
  Orchestrator/workers still must not merge the PR without the user's explicit
  approval after it's opened — pushing the branch and opening the PR is the
  authorized action here, merging the PR is a separate, still-gated step.

## 3. Authoritative agent files

- **Authoritative for this task**: everything under `.agents/` — `plan.md`,
  `AGENT_TEST_REPORT.md`, `AGENT_REVIEW.md`, `AGENT_VALIDATION.md`, `status.md`, this
  file.
- **Not authoritative — stale**: root-level `AGENT_REVIEW.md`, `AGENT_TEST_REPORT.md`,
  `AGENT_VALIDATION.md`. Already-committed leftovers from the prior, separately
  merged `v1-xlsx-style-poc` task (`bc762a7`), describing `set_cell_style` only.
  Do not read, edit, or cite them for this bundle's merge decision.

## 4. Exact relay text for active workers

> Harness note: orchestrator coordination follows
> `~/.codex/profiles/orchestrator.md` + `~/.codex/docs/merge-policy.md`. Your own
> role profile is unchanged — keep using `~/.claude/profiles/<your-role>.md` and
> writing to `.agents/*.md` as before. Corrected flow (supersedes the earlier
> local-merge note): this task ships as a **pushed branch + GitHub PR against
> main**, not a local `git merge`. Do not merge locally and do not delete the
> worktree. Treat `.agents/AGENT_REVIEW.md` / `AGENT_TEST_REPORT.md` /
> `AGENT_VALIDATION.md` as the only authoritative artifacts for this task; ignore
> same-named files at the repo root (already-merged, unrelated prior task).

## 5. Open item for orchestrator

Validator already returned PASS. Branch is committed and pushed to `origin`; a
PR against `main` has been opened via `gh pr create` (see PR URL reported to the
user). Next gate is the user's explicit approval to merge the PR — do not merge
the PR or delete the worktree until that approval is given.
