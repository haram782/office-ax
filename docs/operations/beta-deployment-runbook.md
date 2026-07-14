# Beta deployment hardening runbook

이 문서는 단일 Mac Docker Compose beta 운영 절차다. 실제 secret, domain, tunnel, deploy, restore 작업은 운영 승인과 별도 변경 창 없이는 수행하지 않는다. 호스트의 `8080` 포트를 인터넷에 직접 공개하지 않고, 신뢰한 HTTPS tunnel만 `X-Forwarded-Proto`를 주입하도록 제한한다.

## 1. 준비와 중단 조건

1. `.env.beta.example`을 복사해 Git 밖의 `.env.beta`에 실제 값을 넣는다. 예시 값은 사용하지 않는다.
2. `BETA_RELEASE_TAG`는 배포할 Git SHA 같은 immutable tag로 정한다.
3. Docker Desktop에 Compose resource cap 합계 이상의 CPU/memory와 최소 10 GiB 여유 디스크가 있는지 확인한다.
4. 다음 중 하나면 중단한다: preflight 실패, backup set 미완성, migration plan 미검토, 기존 서비스 restart loop/OOM, 독립 review의 blocking finding, restore rehearsal 미완료.

```bash
./scripts/beta_preflight.sh
```

성공 증거는 `preflight 통과`와 `docker compose config --quiet` 성공이다. 스크립트는 secret 값을 출력하지 않는다.

## 2. 배포

변경 창에서만 아래 controlled recreate를 실행한다. web startup은 migration을 실행하지 않으며 deploy script만 backup 후 migration을 한 번 적용한다.

```bash
./scripts/beta_deploy.sh <git-sha-release-tag>
```

스크립트는 DB+media backup, immutable image build, `check --deploy`, migration plan, migration, service recreate, release manifest 기록 순서로 실행한다. 실패하면 즉시 추가 명령을 멈추고 서비스 상태와 backup set을 보존한다.

## 3. 배포 후 smoke

- `docker compose ... ps`에서 postgres, redis, backend-web, backend-worker, ax-worker, nginx가 healthy인지 확인한다. beat는 PID health와 scheduler 로그를 확인한다.
- `/healthz`는 200, DB 또는 Redis를 격리한 disposable rehearsal의 `/readyz`는 503이어야 한다.
- 비로그인 `/media/uploads/...`, 다른 사용자의 URL, `/_protected_media/...` 직접 요청은 bytes를 반환하지 않아야 한다.
- owner 계정에서 PDF Range/HEAD, HWP fetch, image/PPTX/DOCX preview, 원본/수정본/RAG download, cache-busting query를 확인한다.
- logout 직후 같은 media URL 요청이 실패하는지 확인한다.
- container restart count, OOM event, nginx/backend 5xx가 발생하면 승인하지 않고 rollback 판단으로 이동한다.

## 4. Backup

```bash
BETA_BACKUP_DIR=/approved/absolute/path ./scripts/beta_backup.sh
```

성공한 `backup-<UTC timestamp>` 디렉터리에는 `database.sql.gz`, `media.tar.gz`, `manifest.txt`, `SHA256SUMS`가 모두 있어야 한다. `.partial-*`는 성공 세트가 아니다. writer를 잠시 quiesce하고 원래 실행 중이던 서비스만 trap에서 재시작한다.

## 5. Guarded restore rehearsal

실제 beta volume에서 먼저 실행하지 않는다. 별도 project name과 disposable volume을 복제한 격리 환경에서 backup → 데이터 변경 → restore → readiness/media owner/Range 검증을 끝낸다. 검증된 명시적 set만 사용한다.

```bash
./scripts/beta_restore.sh /approved/backup-set --confirm
```

restore는 checksum, manifest, gzip/tar readability, disk를 먼저 검사하고, 현재 상태 safety backup 후 writer 정지, DB/media 교체, migration compatibility 확인, service 시작 순으로 진행한다. 실패 시 출력된 safety backup을 보존하고 원인을 확인하기 전 서비스를 임의 재시작하지 않는다.

## 6. Rollback

schema 변화가 없거나 additive/backward-compatible migration임을 review에서 확인한 경우에만 명시적 release manifest로 code rollback한다.

```bash
./scripts/beta_rollback.sh <previous-release-tag> --confirm-compatible
```

destructive/irreversible migration 또는 media layout 변화가 있으면 code-only rollback과 임의 `migrate <old target>`을 금지한다. 검증된 DB+media backup set restore를 선택한다. reverse migration은 데이터 손실이 없다고 별도 rehearsal한 경우에만 수동 승인한다.

## 7. 장애 대응

- BOLA 의심: 외부 tunnel을 차단하고 증거를 보존한다. public media alias로 되돌리지 않는다.
- readiness 실패: dependency 이름만 확인하고 DB/Redis health, disk, OOM/restart loop를 조사한다.
- backup 실패: partial set을 사용하지 않고 writer가 원래 상태로 복구됐는지 확인한다.
- secret/token 노출 의심: 로그를 즉시 지우기보다 접근을 제한하고 incident 증거를 보존한 뒤 secret rotation을 승인받는다.
- HSTS: 실제 HTTPS와 redirect loop smoke가 안정될 때만 seconds를 단계적으로 늘린다. 외부 domain 검증 전 includeSubDomains/preload는 활성화하지 않는다.
