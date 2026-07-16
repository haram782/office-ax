#!/usr/bin/env bash
# beta 입력은 docker-compose.beta.yml, .env.beta, --project-directory로 고정한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATIC_ONLY=0
while (($#)); do
    case "$1" in
        --env-file) BETA_ENV_FILE="$2"; shift 2 ;;
        --static-only) STATIC_ONLY=1; shift ;;
        *) echo "[preflight] 알 수 없는 인자: $1" >&2; exit 2 ;;
    esac
done
export BETA_ENV_FILE
# shellcheck source=beta_common.sh
source "$SCRIPT_DIR/beta_common.sh"

errors=0
fail_var() { echo "[preflight] unsafe: $1" >&2; errors=$((errors + 1)); }
require_file "$ENV_FILE"

required=(DJANGO_SECRET_KEY DEBUG ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS DB_PASSWORD BETA_DB_PASSWORD REDIS_URL BETA_ACCESS_MODE VITE_GOOGLE_CLIENT_ID BETA_RELEASE_TAG)
for key in "${required[@]}"; do
    value="$(env_value "$key")"
    [[ -n "$value" ]] || fail_var "$key"
    [[ ! "$value" =~ (change-me|replace-with|your-|\.invalid) ]] || fail_var "$key"
done

[[ "$(env_value DEBUG)" == "False" ]] || fail_var DEBUG
[[ "$(env_value CSRF_TRUSTED_ORIGINS)" == https://* ]] || fail_var CSRF_TRUSTED_ORIGINS
[[ "$(env_value DB_PASSWORD)" == "$(env_value BETA_DB_PASSWORD)" ]] || fail_var DB_PASSWORD/BETA_DB_PASSWORD
validate_release_tag "$(env_value BETA_RELEASE_TAG)" || errors=$((errors + 1))

case "$(env_value BETA_ACCESS_MODE)" in
    allowlist)
        [[ -n "$(env_value BETA_ALLOWED_EMAILS)" ]] || fail_var BETA_ALLOWED_EMAILS
        ;;
    open) ;;
    *) fail_var BETA_ACCESS_MODE ;;
esac

case "$(env_value LLM_PROVIDER)" in
    openai)
        provider_key="$(env_value OPENAI_API_KEY)"
        [[ -n "$provider_key" && ! "$provider_key" =~ (change-me|replace-with) ]] || fail_var OPENAI_API_KEY
        ;;
    anthropic)
        provider_key="$(env_value ANTHROPIC_API_KEY)"
        [[ -n "$provider_key" && ! "$provider_key" =~ (change-me|replace-with) ]] || fail_var ANTHROPIC_API_KEY
        ;;
    *) fail_var LLM_PROVIDER ;;
esac

backup_dir="$(env_value BETA_BACKUP_DIR)"
[[ "$backup_dir" == /* ]] || fail_var BETA_BACKUP_DIR
[[ "$backup_dir" != /absolute/path/* ]] || fail_var BETA_BACKUP_DIR

for key in BETA_POSTGRES_MEMORY BETA_REDIS_MEMORY BETA_BACKEND_WEB_MEMORY BETA_BACKEND_WORKER_MEMORY BETA_BACKEND_BEAT_MEMORY BETA_AX_WORKER_MEMORY BETA_NGINX_MEMORY; do
    value="$(env_value "$key")"
    [[ -z "$value" || "$value" =~ ^[1-9][0-9]*(m|g)$ ]] || fail_var "$key"
done

if [[ "$STATIC_ONLY" -eq 0 ]]; then
    command -v docker >/dev/null || { echo "[preflight] docker를 찾을 수 없습니다." >&2; exit 1; }
    compose config --quiet
    [[ -d "$backup_dir" && -w "$backup_dir" ]] || { echo "[preflight] BETA_BACKUP_DIR 준비 필요" >&2; errors=$((errors + 1)); }
    disk_target="$backup_dir"
    [[ -d "$disk_target" ]] || disk_target="$REPO_ROOT"
    available_kb="$(df -Pk "$disk_target" | awk 'NR==2 {print $4}')"
    configured_disk_kb="$(env_value BETA_MIN_FREE_DISK_KB)"
    required_kb="${BETA_MIN_FREE_DISK_KB:-${configured_disk_kb:-10485760}}"
    [[ "$available_kb" -ge "$required_kb" ]] || { echo "[preflight] disk capacity 부족" >&2; errors=$((errors + 1)); }
    docker_memory="$(docker info --format '{{.MemTotal}}')"
    docker_cpus="$(docker info --format '{{.NCPU}}')"
    memory_bytes() {
        local value="$1" number unit
        number="${value%[mg]}"
        unit="${value: -1}"
        [[ "$unit" == "g" ]] && echo $((number * 1024 * 1024 * 1024)) || echo $((number * 1024 * 1024))
    }
    memory_total=0
    for pair in \
        BETA_POSTGRES_MEMORY:768m BETA_REDIS_MEMORY:256m BETA_BACKEND_WEB_MEMORY:1536m \
        BETA_BACKEND_WORKER_MEMORY:3g BETA_BACKEND_BEAT_MEMORY:384m BETA_AX_WORKER_MEMORY:4g BETA_NGINX_MEMORY:256m; do
        key="${pair%%:*}"; fallback="${pair#*:}"; value="$(env_value "$key")"; value="${value:-$fallback}"
        memory_total=$((memory_total + $(memory_bytes "$value")))
    done
    [[ "$docker_memory" -ge "$memory_total" ]] || { echo "[preflight] Docker memory capacity 부족" >&2; errors=$((errors + 1)); }
    cpu_total="$(for pair in BETA_POSTGRES_CPUS:1.0 BETA_REDIS_CPUS:0.5 BETA_BACKEND_WEB_CPUS:1.5 BETA_BACKEND_WORKER_CPUS:2.0 BETA_BACKEND_BEAT_CPUS:0.5 BETA_AX_WORKER_CPUS:2.0 BETA_NGINX_CPUS:0.5; do key="${pair%%:*}"; fallback="${pair#*:}"; value="$(env_value "$key")"; echo "${value:-$fallback}"; done | awk '{sum += $1} END {print sum}')"
    awk -v available="$docker_cpus" -v required="$cpu_total" 'BEGIN {exit !(available >= required)}' || { echo "[preflight] Docker CPU capacity 부족" >&2; errors=$((errors + 1)); }
fi

if [[ "$errors" -ne 0 ]]; then
    echo "[preflight] ${errors}개 조건을 수정해야 합니다. 값은 보안상 출력하지 않았습니다." >&2
    exit 1
fi
echo "[preflight] 통과"
