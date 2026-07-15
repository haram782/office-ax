# Beta deployment hardening implementation handoff

## Implementation summary (round 1 fixes applied on top of 3de277e)

- `/media/...` compatibility를 유지하면서 session 인증과 namespace별 exact ownership을 적용하고, nginx `internal` location으로만 파일 bytes를 전달한다.
- Google login은 DRF token과 Django session을 함께 수립하고 logout/동의 거부는 token과 session을 함께 종료한다.
- proxy HTTPS, secure cookie, staged HSTS, DB/Redis readiness와 dependency-free liveness를 추가했다.
- Compose에서 web 자동 migration을 제거하고 immutable release tag, service healthcheck, resource cap, bounded JSON logs를 구성했다.
- beta compose/env를 고정한 preflight, DB+media backup, checksum/manifest guarded restore, controlled deploy/rollback과 운영 runbook을 추가했다.
- model/schema migration과 제품 기능 확장은 없다. tracked `AGENT_PLAN.md`, `AGENT_FAILURES.md`, `.agents/`는 수정하지 않았다.

### Round 1: reviewer BLOCKING/HIGH 조치

1. **media gateway method 제한 (BLOCKING)**: `backend/apps/documents/media.py`의 `protected_media`에 `@require_http_methods(["GET", "HEAD"])`를 추가해 POST/PUT/PATCH/DELETE/OPTIONS를 애플리케이션 레이어에서 405로 거부한다. `infra/nginx/beta.conf`의 `/_protected_media/` internal location에도 `limit_except GET HEAD { deny all; }`를 추가해 nginx 레벨 안전망을 명시적으로 갖췄다(이전에는 `ngx_http_static_module` 기본 동작에만 암묵적으로 의존).
2. **namespace별 BOLA negative 테스트 (BLOCKING)**: `backend/apps/documents/tests_media_access.py`에 `DocumentVersion.artifact_file`, `ChatMessage.artifact_url`, legacy `UploadLog.result.artifact_url`, `slides/<upload_id>/...`, `docx_pdf/<upload_id>/...`, exact RAG file 각각에 대해 다른 사용자가 접근 시 404를 확인하는 6개 테스트를 추가했다. method 거부 테스트(`test_write_methods_are_rejected_regardless_of_ownership`)도 함께 추가했다(12 tests, 이전 6개).
3. **ops 실패 경로 실행형 테스트 (HIGH)**: `scripts/tests/fake_docker.sh`(신규), `scripts/tests/fake_df.sh`(신규)로 실제 docker 없이 `docker compose ...` 호출을 가로채는 fake 실행기를 만들고, `scripts/tests/test_beta_ops.py`에 `BetaOpsFakeDockerExecutionTest` 클래스(8개 테스트)를 추가했다: 정상 backup/restore round-trip, pg_dump/media-tar 실패 시 writer 복구와 `.partial-*` 미승격, restore의 checksum/manifest/디스크 부족 실패가 `dropdb`/`createdb` 호출 전에 중단됨을 명령 로그로 직접 검증.
4. **restore symlink entry 거부**: `scripts/beta_restore.sh`에 `tar -tvzf`로 media archive의 symlink(`l` type) entry를 검사해 거부하는 단계를 추가하고, 대응 테스트(`test_restore_rejects_symlink_entry_in_media_archive`)를 추가했다.
5. **부수 수정**: `scripts/beta_backup.sh`의 `FINAL` 디렉터리 이름에 PID(`$$`)를 추가해, 같은 초에 연속 실행되는 backup(예: restore의 safety backup)이 이전 backup set 디렉터리 안으로 병합(nesting)되지 않고 항상 독립된 complete set으로 남도록 했다(fake-docker 실행형 restore round-trip 테스트로 발견/검증됨).

## Tests and evidence (round 1 재실행)

- Backend focused: `apps.accounts apps.documents.tests_media_access config.tests_health config.tests_security` → **37/37 PASS**(기존 30 + media 신규 7).
- Backend full: `manage.py test --settings=config.settings_test` → **459/459 PASS**(기존 452 + 7).
- Frontend: `npx vitest run --run` → **217/217 PASS**(32 files, 변경 없음).
- Ops: `python3 -m unittest scripts.tests.test_beta_ops -v` → **16/16 PASS**(기존 8 + fake-docker 실행형 8).
- Shell: 6개 beta 스크립트 전부 `bash -n` PASS.
- YAML: `docker-compose.beta.yml` safe_load PASS, 7 services.
- `manage.py check --deploy --fail-level ERROR`(production-like dummy env) → **exit 0**, 19 warnings(drf-spectacular 추론 17 + 의도적 HSTS 보류 2), 이전과 동일.
- `manage.py makemigrations --check --dry-run` → `No changes detected`.
- `git diff --check` → clean.
- Docker CLI 부재로 실제 nginx runtime smoke(POST/PUT/DELETE가 실제로 405/차단되는지, X-Accel internal 직접 접근 차단, Range/HEAD)와 disposable backup/restore round-trip은 여전히 미실행. 이 round은 fake-docker 실행형 host 테스트로 ops 실패 복구 로직을 실행 검증했지만, 실제 컨테이너 기반 검증을 대체하지 않는다.

## Review handoff

- 이전 리뷰의 두 BLOCKING(media method 미제한, namespace별 BOLA negative 누락)과 HIGH(ops 실패 경로 실행형 테스트 부족) 항목을 모두 조치했다.
- 독립 reviewer는 이번 라운드에서: (1) `require_http_methods` guard와 nginx `limit_except`가 실제로 POST/PUT/PATCH/DELETE/OPTIONS를 차단하는지(코드 레벨), (2) 6개 신규 BOLA 테스트가 계획의 Red/Green matrix를 실제로 충족하는지, (3) fake-docker 테스트가 checksum/manifest/디스크/symlink 실패를 destructive 단계(`dropdb`/`createdb`) 이전에 정확히 차단하는지, (4) `beta_backup.sh`의 FINAL 디렉터리 PID suffix 변경이 retention/naming 계약을 깨지 않는지를 우선 재확인해야 한다.
- Residual runtime gate(Docker 미설치로 인한 실제 nginx/컨테이너 검증)는 이전과 동일하게 별도 트랙으로 남아 있다. `check --deploy`의 20 warnings(원문 22와 실측 19의 차이는 dummy env 구성 차이이며 ERROR는 없음)에 대한 이전 서술은 이번 재실행 결과(19)로 갱신했다.

## Implementation summary (round 2 fixes applied on top of 67f840c)

실제 Docker runtime rehearsal에서 재현된 4개 차단점을 수정했다. 실제 Docker 리소스는 건드리지 않았고 merge는 하지 않았다.

1. **nginx healthcheck IPv6/IPv4 불일치**: `docker-compose.beta.yml`의 nginx healthcheck가 `http://localhost/healthz`를 사용해 Alpine wget이 `::1`(IPv6)을 먼저 시도했지만 nginx는 IPv4만 listen해 `Connection refused`로 항상 실패했다. `http://127.0.0.1/healthz`로 고정했다. `scripts/tests/test_beta_ops.py::test_nginx_healthcheck_uses_ipv4_localhost`로 계약을 고정했다.
2. **protected media Content-Type 누락**: `backend/apps/documents/media.py`의 `protected_media`가 `HttpResponse()`를 기본 `text/html; charset=utf-8`로 생성해, nginx `X-Accel-Redirect` internal redirect가 이 Content-Type을 그대로 보존했다(owner PDF GET/HEAD/Range가 200/206이지만 body가 HTML로 해석됨). 파일명 확장자 기반 allowlist(`_SAFE_CONTENT_TYPES`, unknown은 `application/octet-stream`)로 안전한 MIME을 명시하도록 수정했다. `backend/apps/documents/tests_media_access.py`에 PDF/PNG/unknown 확장자 3개 단위 테스트를 추가했다.
3. **restore media 이중 gzip 해제**: `scripts/beta_restore.sh`가 `gzip -dc media.tar.gz | tar -xzf -`로 이미 해제된 스트림을 다시 gzip으로 풀려고 시도해 media 복원이 항상 실패했다(media volume이 빈 채로 남고 backend-web이 Exited 137). `tar -xf -`(단일 gzip 계층)로 수정했다. `scripts/tests/fake_docker.sh`의 대응 case pattern도 함께 갱신했다. 정적 계약 테스트 2개(`-xzf` 부재, `-xf` 존재)와 실제 gzip/tar 바이너리로 파이프라인 자체를 검증하는 실행형 테스트(`test_restore_media_extraction_command_handles_real_gzip_tar_stream`)를 추가했다.
4. **destructive 단계 실패 후 fail-open 위험**: writer 정지(destructive 단계) 이후 실패해도 자동으로 writer를 재기동하지 않도록 `on_exit` trap을 추가했다. `DESTRUCTIVE_STARTED`/`SUCCESS` 플래그로 destructive 단계 진입 여부와 성공 여부를 추적하고, 실패 시 stderr에 safety backup 경로, restore target, 복구 지침(`writer 수동 재기동 전 DB/media 일관성 확인` 포함)을 출력한다. fake-docker 실행형 테스트(`test_restore_failure_after_destructive_step_stays_fail_closed`)로 destructive 단계 진입 후 실패해도 `start`/`up -d` writer 명령이 로그에 남지 않음을 검증했다.
5. **runbook backup 이름 동기화**: `docs/operations/beta-deployment-runbook.md`의 `backup-<UTC timestamp>` 표기를 실제 스크립트 계약(`backup-<UTC timestamp>-<PID>`, round 1에서 이미 PID suffix 도입)에 맞춰 갱신했다.

### Tests and evidence (round 2)

- Backend focused: `apps.accounts apps.documents.tests_media_access config.tests_health config.tests_security --settings=config.settings_test` → **40/40 PASS**(기존 37 + Content-Type 신규 3).
- Backend full: `manage.py test --settings=config.settings_test` → **462/462 PASS**(기존 459 + 3).
- Frontend: `npx vitest run` → **217/217 PASS**(32 files, 변경 없음, 회귀 스모크).
- Ops: `python3 -m unittest scripts.tests.test_beta_ops -v` → **21/21 PASS**(기존 16 + nginx healthcheck 1 + restore gzip/tar 정적·실행형 3 + fail-closed 정적·실행형 2, 중 1개는 배포된 fake-docker 실행형).
- Shell: `scripts/*.sh`, `scripts/tests/*.sh` 전부 `bash -n` PASS.
- YAML: `docker-compose.beta.yml` `.venv`의 PyYAML로 `safe_load` PASS.
- nginx 문법 검사(`nginx -t`)는 로컬에 nginx 바이너리가 없어 미실행 — 변경이 healthcheck URL 문자열 1곳(`beta.conf`는 무변경)뿐이라 리스크는 낮지만, 실제 Docker rehearsal에서 nginx reload 확인이 필요하다.
- 실제 Docker 컨테이너 기반 재현(healthz 200, PDF Content-Type, restore round-trip, destructive 실패 후 writer 상태)은 orchestrator 지시에 따라 이번 라운드에서 실행하지 않았다 — 정적 계약 테스트와 fake-docker/real gzip-tar 실행형 테스트로 대체 검증했다. 다음 실제 Docker rehearsal에서 이 4개 지점을 우선 재확인해야 한다.

### Review handoff (round 2)

- 독립 reviewer는: (1) `_SAFE_CONTENT_TYPES`가 실제 서비스되는 모든 확장자를 포함하는지(누락 시 안전하게 `application/octet-stream`로 fallback), (2) `on_exit` trap이 `set -euo pipefail`과 상호작용해 원래 실패 exit code를 보존하는지, (3) fake-docker 로그 기반 테스트가 restore 자체의 `stop -t 60`과 safety-backup 내부의 `stop`/`start`를 정확히 구분하는지(safety backup은 자신의 snapshot을 위해 독립적으로 writer를 잠깐 멈췄다 되돌린다)를 우선 확인해야 한다.

## Follow-up: SVG active-content 보정 (HEAD b844540 이후)

- `backend/apps/documents/media.py`의 `_SAFE_CONTENT_TYPES`에서 `.svg`를 제거하는 미커밋 diff가 이전 세션에서 남아 있었다(same-origin `image/svg+xml`은 인라인 `<script>`/이벤트 핸들러로 저장형 XSS가 가능해짐). SVG는 이제 unknown 확장자와 동일하게 `application/octet-stream` fallback으로 강제 다운로드된다.
- `backend/apps/documents/tests_media_access.py`에 `test_svg_falls_back_to_octet_stream_not_active_content` 1개를 추가해, `<svg onload="alert(1)">` 페이로드를 업로드해도 응답 Content-Type이 `application/octet-stream`임을 검증했다. 기존 `test_unknown_extension_falls_back_to_octet_stream`, PDF/PNG Content-Type 테스트는 그대로 유지했다.
- Backend focused(`apps.documents.tests_media_access --settings=config.settings_test`): **16/16 PASS**(기존 15 + SVG 신규 1).
- Backend full(`manage.py test --settings=config.settings_test`): **463/463 PASS**(기존 462 + 1).
- 이번 후속 작업은 media.py의 allowlist 미커밋 diff를 커밋에 포함하고 테스트만 추가했다 — merge는 하지 않았다.

## Round 3: 실제 Docker rehearsal restore stop/start 재발 재현 (HEAD 0d3fedb 이후)

실제 Docker rehearsal에서 전체 7서비스 최초 healthy, backup→mutate→restore까지는 성공했으나, restore의 `compose stop` 이후 같은 `backend-beat` 컨테이너를 `start`/`up` 하는 단계에서 재발이 관찰됐다. 실제 Docker 리소스는 건드리지 않았고 merge는 하지 않았다.

- **재현 증상**: `compose stop`은 컨테이너를 제거하지 않으므로 celery beat가 이전에 남긴 `/tmp/celerybeat.pid`가 컨테이너의 writable layer에 그대로 남는다. 이후 같은 컨테이너를 `start`/`up` 하면 celery beat가 시작 시 `--pidfile=/tmp/celerybeat.pid`가 이미 존재한다고 보고 `ERROR: Pidfile (/tmp/celerybeat.pid) already exists` → `exit 73` → `restart: unless-stopped` 정책에 의한 재시작 루프(113회 관찰)에 빠진다.
- **조치**: `docker-compose.beta.yml`의 `backend-beat` `command`를 `celery -A config beat --pidfile=...` 단일 명령에서 `sh -c "rm -f /tmp/celerybeat.pid && exec celery -A config beat --loglevel=info --pidfile=/tmp/celerybeat.pid"`로 감쌌다. `exec`를 사용해 celery가 PID 1을 그대로 이어받게 해 `docker stop`의 SIGTERM 전달 경로(shell wrapper가 신호를 가로채지 않음)를 보존했다. healthcheck(`test -r /tmp/celerybeat.pid && kill -0 ...`)는 변경하지 않았다 — pidfile은 celery beat 자신이 기동 시 재생성하므로 healthcheck 계약과 충돌하지 않는다.
- **테스트**: `scripts/tests/test_beta_ops.py`에 정적 계약 테스트(`test_backend_beat_command_clears_stale_pidfile_before_exec`, command가 `sh -c`로 시작하고 `rm -f`가 `exec celery`보다 먼저 오는지, `healthcheck`/`mem_limit`/`cpus`/`logging`이 모두 존재하는지 확인)와, 실제 `sh -c`로 command 문자열 자체를 실행해 stale pidfile이 celery 실행 전에 제거되는지 검증하는 실행형 테스트(`test_backend_beat_pidfile_cleanup_runs_against_real_shell`, 가짜 `celery` 바이너리로 pidfile 부재 시점을 마커 파일로 확인)를 추가했다(21 → 23).

### Tests and evidence (round 3)

- Ops: `python3 -m unittest scripts.tests.test_beta_ops -v` → **23/23 PASS**(기존 21 + backend-beat pidfile 정적·실행형 2).
- Shell: `scripts/*.sh` 전부 `bash -n` PASS(무변경, 회귀 확인).
- YAML: `docker-compose.beta.yml`을 `.venv`의 PyYAML `safe_load`로 파싱해 `backend-beat.command`/`healthcheck` 값이 의도대로 반영됐는지 확인 → PASS.
- 이번 라운드는 `docker-compose.beta.yml`과 ops 테스트만 수정했다 — backend/frontend 소스는 변경하지 않아 별도 회귀 실행은 생략했다(직전 라운드 backend 463/463, frontend 217/217은 무변경 상태로 유효).
- 실제 Docker 컨테이너로 이 수정(stop→start 반복 후 `backend-beat`가 healthy로 안정화되는지)을 재확인하는 것은 이번 세션 범위 밖이다 — 다음 실제 Docker rehearsal에서 최우선으로 재확인해야 한다.

### Review handoff (round 3)

- 독립 reviewer는: (1) `sh -c` wrapper가 `exec`를 사용해 SIGTERM이 shell이 아닌 celery beat 프로세스로 직접 전달되는지(그렇지 않으면 `compose stop`의 graceful shutdown이 깨질 수 있음), (2) healthcheck가 `rm -f` 직후 짧은 창(celery가 아직 pidfile을 재생성하기 전)에 거짓 unhealthy로 오판하지 않는지(`start_period` 미설정 상태이므로 `retries: 5`, `interval: 30s`로 흡수 가능한지), (3) `command:` 값의 YAML 큰따옴표 이스케이프가 실제 Docker Compose 파서에서도 `docker-compose.beta.yml`을 PyYAML로 파싱한 것과 동일하게 해석되는지를 우선 확인해야 한다.
