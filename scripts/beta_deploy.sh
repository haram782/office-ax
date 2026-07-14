#!/usr/bin/env bash
# beta 입력은 docker-compose.beta.yml, .env.beta, --project-directory로 고정한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_TAG="${1:-}"
[[ -n "$RELEASE_TAG" ]] || { echo "사용법: beta_deploy.sh <release-tag>" >&2; exit 2; }
# shellcheck source=beta_common.sh
source "$SCRIPT_DIR/beta_common.sh"
validate_release_tag "$RELEASE_TAG"

"$SCRIPT_DIR/beta_preflight.sh"
backup_set="$($SCRIPT_DIR/beta_backup.sh)"
mkdir -p "$REPO_ROOT/.releases"
previous_tag="$(test -f "$REPO_ROOT/.releases/current.env" && awk -F= '$1=="release_tag" {print $2}' "$REPO_ROOT/.releases/current.env" || true)"
export BETA_RELEASE_TAG="$RELEASE_TAG"

compose build backend-web backend-worker backend-beat ax-worker nginx
compose run --rm --no-deps backend-web python manage.py check --deploy
compose run --rm --no-deps backend-web python manage.py showmigrations --plan
compose stop -t 60 backend-web backend-worker backend-beat ax-worker
compose run --rm --no-deps backend-web python manage.py migrate --noinput
compose up -d --remove-orphans

cat >"$REPO_ROOT/.releases/$RELEASE_TAG.env" <<EOF
release_tag=$RELEASE_TAG
previous_tag=$previous_tag
backup_set=$backup_set
deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
cp "$REPO_ROOT/.releases/$RELEASE_TAG.env" "$REPO_ROOT/.releases/current.env"
compose ps
echo "[deploy] $RELEASE_TAG 배포 완료. runbook smoke 후 승인하세요."
