#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.beta.yml"
ENV_FILE="${BETA_ENV_FILE:-$REPO_ROOT/.env.beta}"
PROJECT_NAME="officeax-beta"

compose() {
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --project-directory "$REPO_ROOT" "$@"
}
env_value() {
    local key="$1"
    awk -F= -v key="$key" '$0 !~ /^[[:space:]]*#/ && $1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

require_file() {
    if [[ ! -f "$1" ]]; then
        echo "[beta] 필수 파일이 없습니다: $1" >&2
        return 1
    fi
}

validate_release_tag() {
    [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{6,63}$ ]] || {
        echo "[beta] BETA_RELEASE_TAG는 7~64자의 immutable tag여야 합니다." >&2
        return 1
    }
}
