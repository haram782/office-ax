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
# symlink entry는 extraction 시점에 media root 밖을 가리킬 수 있어 destructive 단계 전에 거부한다.
tar -tvzf "$BACKUP_SET/media.tar.gz" | awk '$1 ~ /^l/ {bad=1} END {exit bad}' || {
    echo "[restore] media archive에 symlink entry가 포함되어 있어 거부합니다." >&2
    exit 1
}

required_kb="$(du -sk "$BACKUP_SET" | awk '{print $1 * 3}')"
available_kb="$(df -Pk "$REPO_ROOT" | awk 'NR==2 {print $4}')"
[[ "$available_kb" -ge "$required_kb" ]] || { echo "[restore] disk capacity 부족" >&2; exit 1; }

DESTRUCTIVE_STARTED=0
SUCCESS=0
safety_set=""

# destructive 단계(writer 정지 이후) 실패 시 writer를 임의로 재기동하지 않는다.
# 재기동은 DB/media가 일부만 교체된 불일치 상태를 서비스에 그대로 노출할 수 있어
# fail-closed로 정지 상태를 유지하고, 복구에 필요한 safety backup/target을 출력한다.
on_exit() {
    local status=$?
    if ((status != 0)) && ((DESTRUCTIVE_STARTED == 1)) && ((SUCCESS == 0)); then
        {
            echo "[restore] 실패: destructive 단계 진행 중 오류가 발생했습니다."
            echo "[restore] writer(backend-web/backend-worker/backend-beat/ax-worker)는 fail-closed로 정지 상태를 유지합니다. 임의로 재기동하지 않습니다."
            echo "[restore] safety backup: ${safety_set:-<생성 전 실패>}"
            echo "[restore] restore target: $BACKUP_SET"
            echo "[restore] 복구 지침: 원인을 조사한 뒤 원래 상태로 되돌리려면 './scripts/beta_restore.sh ${safety_set:-<safety-set>} --confirm'을 실행하거나, 문제를 해결한 뒤 동일 대상으로 재시도하세요. writer를 수동으로 재기동하기 전에 DB/media 상태 일관성을 먼저 확인하세요."
        } >&2
    fi
    return "$status"
}
trap on_exit EXIT

# 파괴 단계 전에 현재 상태를 별도 complete set으로 보존한다.
safety_set="$($SCRIPT_DIR/beta_backup.sh)"
echo "[restore] safety backup: $safety_set"
DESTRUCTIVE_STARTED=1
compose stop -t 60 backend-web backend-worker backend-beat ax-worker

db_name="$(env_value DB_NAME)"
db_user="$(env_value DB_USER)"
compose exec -T postgres dropdb -U "${db_user:-postgres}" --if-exists "${db_name:-officeax_beta}"
compose exec -T postgres createdb -U "${db_user:-postgres}" "${db_name:-officeax_beta}"
gzip -dc "$BACKUP_SET/database.sql.gz" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${db_user:-postgres}" "${db_name:-officeax_beta}"
compose run --rm --no-deps backend-web sh -c 'find /app/backend/media -mindepth 1 -delete'
# gzip -dc가 이미 압축을 해제하므로 tar는 단일 gzip 계층만 기대하는 -xf로 받아야 한다.
# 여기서 -xzf를 다시 쓰면 이중 gzip 해제를 시도해 media 복원이 항상 실패한다.
gzip -dc "$BACKUP_SET/media.tar.gz" | compose run --rm --no-deps -T backend-web tar -C /app/backend/media -xf -
compose run --rm --no-deps backend-web python manage.py showmigrations --plan
compose up -d backend-web backend-worker backend-beat ax-worker nginx
compose exec -T backend-web curl -fsS -H 'X-Forwarded-Proto: https' http://localhost:8000/readyz >/dev/null
SUCCESS=1
echo "[restore] 완료. media owner/Range smoke를 runbook에 따라 확인하세요."
