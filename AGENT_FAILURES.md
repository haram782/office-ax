# AGENT_FAILURES.md

## 2026-07-13 — untracked coordination file handoff

- Failure: `create-worktree-with-diff.sh` did not hand off an untracked `AGENT_PLAN.md`, leaving `main` dirty.
- Prevention: detect and include untracked files during dirty-worktree handoff, or pre-add coordination files before creating the worktree.
