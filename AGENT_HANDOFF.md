# Beta deployment hardening implementation handoff

## Implementation summary

- `/media/...` compatibility를 유지하면서 session 인증과 namespace별 exact ownership을 적용하고, nginx `internal` location으로만 파일 bytes를 전달한다.
- Google login은 DRF token과 Django session을 함께 수립하고 logout/동의 거부는 token과 session을 함께 종료한다.
- proxy HTTPS, secure cookie, staged HSTS, DB/Redis readiness와 dependency-free liveness를 추가했다.
- Compose에서 web 자동 migration을 제거하고 immutable release tag, service healthcheck, resource cap, bounded JSON logs를 구성했다.
- beta compose/env를 고정한 preflight, DB+media backup, checksum/manifest guarded restore, controlled deploy/rollback과 운영 runbook을 추가했다.
- model/schema migration과 제품 기능 확장은 없다. tracked `AGENT_PLAN.md`, `AGENT_FAILURES.md`, `.agents/`는 수정하지 않았다.

## Tests and evidence

- Red evidence: 구현 전 `python3 -m unittest scripts.tests.test_beta_ops -v`는 6개 계약이 모두 실패했다.
- Green: backend focused 30/30, backend full 452/452 통과(Python 3.12 worktree `.venv`).
- Green: frontend focused 39/39, frontend full 217/217, production build 통과(`npm ci` lockfile install).
- Green: ops/static 계약 8/8, 모든 beta shell script `bash -n`, 변경 Python compile, Compose YAML safe parse, `git diff --check` 통과.
- Green: `manage.py makemigrations --check --dry-run`은 `No changes detected`.
- Green: `manage.py check --deploy --fail-level ERROR` 통과. API schema 추론 경고는 기존 범위이며, HSTS includeSubDomains/preload는 외부 domain smoke 전 의도적으로 비활성화했다.
- Docker validation만 Docker CLI 부재로 compose config, image test, nginx/media Range smoke, disposable backup/restore round-trip 실행 불가.

## Review handoff

독립 reviewer는 media resolver의 exact-name/BOLA/non-enumeration, X-Accel path encoding, session/token logout, shell quoting과 restore archive traversal guard, migration/rollback compatibility gate를 우선 확인해야 한다. 환경 한계로 acceptance criterion 12의 runtime validation과 independent review는 아직 충족되지 않았으므로 orchestrator가 검증하기 전 merge-ready가 아니다.
