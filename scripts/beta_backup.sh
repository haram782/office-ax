#!/usr/bin/env bash
# beta 입력은 docker-compose.beta.yml, .env.beta, --project-directory로 고정한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=beta_common.sh
source "$SCRIPT_DIR/beta_common.sh"

require_file "$ENV_FILE"
configured_backup_dir="$(env_value BETA_BACKUP_DIR)"
BACKUP_DIR="${BETA_BACKUP_DIR:-${configured_backup_dir:-$HOME/officeax-beta-backups}}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PARTIAL="$BACKUP_DIR/.partial-$STAMP-$$"
# PID을 포함해 같은 초에 연속 실행(예: restore의 safety backup)해도 기존 backup set을
# 디렉터리 안으로 병합해버리지 않고 항상 새 complete set으로 남긴다.
FINAL="$BACKUP_DIR/backup-$STAMP-$$"
WRITERS=(backend-web backend-worker backend-beat ax-worker)
RUNNING=()
SUCCESS=0

restore_writers() {
    if ((${#RUNNING[@]})); then
        compose start "${RUNNING[@]}" >/dev/null || true
    fi
    if [[ "$SUCCESS" -ne 1 ]]; then
        rm -rf "$PARTIAL"
    fi
}
trap restore_writers EXIT

mkdir -p "$BACKUP_DIR" "$PARTIAL"
while IFS= read -r service; do
    for writer in "${WRITERS[@]}"; do
        [[ "$service" == "$writer" ]] && RUNNING+=("$writer")
    done
done < <(compose ps --status running --services)

if ((${#RUNNING[@]})); then
    compose stop -t 60 "${RUNNING[@]}" >/dev/null
fi

db_name="$(env_value DB_NAME)"
db_user="$(env_value DB_USER)"
compose exec -T postgres pg_dump -U "${db_user:-postgres}" "${db_name:-officeax_beta}" | gzip >"$PARTIAL/database.sql.gz"
compose run --rm --no-deps -T backend-web tar -C /app/backend/media -czf - . >"$PARTIAL/media.tar.gz"
gzip -t "$PARTIAL/database.sql.gz"
tar -tzf "$PARTIAL/media.tar.gz" >/dev/null

cat >"$PARTIAL/manifest.txt" <<EOF
format=officeax-beta-backup-v1
created_at=$STAMP
release_tag=$(env_value BETA_RELEASE_TAG)
database_file=database.sql.gz
media_file=media.tar.gz
EOF
(cd "$PARTIAL" && shasum -a 256 database.sql.gz media.tar.gz manifest.txt >SHA256SUMS)
mv "$PARTIAL" "$FINAL"
SUCCESS=1

# 완료된 backup set 단위로만 보관 정책을 적용한다.
while IFS= read -r old; do rm -rf "$old"; done < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name 'backup-*' -print | sort -r | tail -n +15)
echo "$FINAL"
