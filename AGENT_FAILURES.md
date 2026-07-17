# AGENT_FAILURES.md

## 2026-07-13 — untracked coordination file handoff

- Failure: `create-worktree-with-diff.sh` did not hand off an untracked `AGENT_PLAN.md`, leaving `main` dirty.
- Prevention: detect and include untracked files during dirty-worktree handoff, or pre-add coordination files before creating the worktree.

## 2026-07-16 — Claude implementer Bash permission hook 반복 오류

- Failure: cmux로 생성한 implementer가 할당된 `/private/tmp` worktree의 읽기 전용 Bash 명령에도 `PreToolUse:Bash hook error`를 반복하고 개별 승인 프롬프트를 띄웠다.
- Root cause: `create-worktree-with-diff.sh`가 아닌 경로로 worktree를 재연결해 worker bootstrap이 적용되지 않았고, hook 오류가 non-blocking으로 반복됐다.
- Prevention: worker를 띄우기 전에 launcher가 할당 worktree의 permission bootstrap 상태를 확인하거나, worktree 재배치 시 동일 bootstrap을 재적용한다.
- Harness action: worktree permission bootstrap 검사 및 복구 단계를 spawn script에 추가 검토.
- Evidence: branch `work/local-beta-cli-qa`의 Claude implementer 세션.
- Status: open
