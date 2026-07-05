#!/usr/bin/env bash
# Office-AX 베타 Postgres 일일 백업 스크립트
#
# 사용법:  ./scripts/beta_backup.sh
# 크론 등록 예 (매일 04시 — beat 정리 작업 03시 이후):
#   0 4 * * * /path/to/office-ax/scripts/beta_backup.sh >> ~/officeax-beta-backups/backup.log 2>&1
#
# 보관 정책: 최근 14개 유지, 초과분 삭제

set -euo pipefail

BACKUP_DIR="${BETA_BACKUP_DIR:-$HOME/officeax-beta-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/officeax_beta_$STAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# 컨테이너 안에서 pg_dump 실행 — 호스트에 psql 설치 불필요
docker compose -p officeax-beta exec -T postgres \
    pg_dump -U postgres officeax_beta | gzip > "$OUT"

echo "[beta_backup] 완료: $OUT ($(du -h "$OUT" | cut -f1))"

# 오래된 백업 정리 (최근 14개 유지)
ls -1t "$BACKUP_DIR"/officeax_beta_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
