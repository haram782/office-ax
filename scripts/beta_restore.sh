#!/usr/bin/env bash
# beta 입력은 docker-compose.beta.yml, .env.beta, --project-directory로 고정한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SET="${1:-}"
CONFIRM="${2:-}"
if [[ -z "$BACKUP_SET" || "$CONFIRM" != "--confirm" ]]; then
    echo "사용법: beta_restore.sh <backup-set> --confirm" >&2
    exit 2
fi
# shellcheck source=beta_common.sh
source "$SCRIPT_DIR/beta_common.sh"

require_file "$ENV_FILE"
for file in manifest.txt SHA256SUMS database.sql.gz media.tar.gz; do require_file "$BACKUP_SET/$file"; done
[[ "$(awk '{print $2}' "$BACKUP_SET/SHA256SUMS" | sort | tr '\n' ' ')" == "database.sql.gz manifest.txt media.tar.gz " ]] || {
    echo "[restore] checksum 목록이 허용된 파일과 다릅니다." >&2
    exit 1
}
(cd "$BACKUP_SET" && shasum -a 256 -c SHA256SUMS)
grep -qx 'format=officeax-beta-backup-v1' "$BACKUP_SET/manifest.txt"
gzip -t "$BACKUP_SET/database.sql.gz"
tar -tzf "$BACKUP_SET/media.tar.gz" | awk '/^\// || $0 ~ /(^|\/)\.\.($|\/)/ {bad=1} END {exit bad}'

required_kb="$(du -sk "$BACKUP_SET" | awk '{print $1 * 3}')"
available_kb="$(df -Pk "$REPO_ROOT" | awk 'NR==2 {print $4}')"
[[ "$available_kb" -ge "$required_kb" ]] || { echo "[restore] disk capacity 부족" >&2; exit 1; }

# 파괴 단계 전에 현재 상태를 별도 complete set으로 보존한다.
safety_set="$($SCRIPT_DIR/beta_backup.sh)"
echo "[restore] safety backup: $safety_set"
compose stop -t 60 backend-web backend-worker backend-beat ax-worker

db_name="$(env_value DB_NAME)"
db_user="$(env_value DB_USER)"
compose exec -T postgres dropdb -U "${db_user:-postgres}" --if-exists "${db_name:-officeax_beta}"
compose exec -T postgres createdb -U "${db_user:-postgres}" "${db_name:-officeax_beta}"
gzip -dc "$BACKUP_SET/database.sql.gz" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${db_user:-postgres}" "${db_name:-officeax_beta}"
compose run --rm --no-deps backend-web sh -c 'find /app/backend/media -mindepth 1 -delete'
gzip -dc "$BACKUP_SET/media.tar.gz" | compose run --rm --no-deps -T backend-web tar -C /app/backend/media -xzf -
compose run --rm --no-deps backend-web python manage.py showmigrations --plan
compose up -d backend-web backend-worker backend-beat ax-worker nginx
compose exec -T backend-web curl -fsS -H 'X-Forwarded-Proto: https' http://localhost:8000/readyz >/dev/null
echo "[restore] 완료. media owner/Range smoke를 runbook에 따라 확인하세요."
