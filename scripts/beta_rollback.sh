#!/usr/bin/env bash
# beta 입력은 docker-compose.beta.yml, .env.beta, --project-directory로 고정한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_TAG="${1:-}"
CONFIRM="${2:-}"
if [[ -z "$RELEASE_TAG" || "$CONFIRM" != "--confirm-compatible" ]]; then
    echo "사용법: beta_rollback.sh <release-tag> --confirm-compatible" >&2
    echo "비가역 migration/media 변경이면 beta_restore.sh를 사용하세요." >&2
    exit 2
fi
# shellcheck source=beta_common.sh
source "$SCRIPT_DIR/beta_common.sh"
validate_release_tag "$RELEASE_TAG"
manifest="$REPO_ROOT/.releases/$RELEASE_TAG.env"
require_file "$manifest"
grep -qx "release_tag=$RELEASE_TAG" "$manifest"
export BETA_RELEASE_TAG="$RELEASE_TAG"

compose stop -t 60 backend-web backend-worker backend-beat ax-worker
compose up -d --no-build backend-web backend-worker backend-beat ax-worker nginx
compose exec -T backend-web curl -fsS -H 'X-Forwarded-Proto: https' http://localhost:8000/readyz >/dev/null
cp "$manifest" "$REPO_ROOT/.releases/current.env"
echo "[rollback] $RELEASE_TAG code rollback 완료"
