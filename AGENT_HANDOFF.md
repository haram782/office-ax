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
