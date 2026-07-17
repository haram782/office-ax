#!/usr/bin/env bash
# 로컬 CLI QA 스택 기동: Docker(postgres/redis/backend-web/backend-worker/
# backend-beat/nginx) + 호스트 AX 워커(claude_cli) + cloudflared Quick Tunnel.
# 여러 번 실행해도 안전하다 — 이미 떠 있는 구성요소는 건드리지 않는다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local_beta_common.sh
source "$SCRIPT_DIR/local_beta_common.sh"

require_file "$ENV_FILE" || {
    echo "[start] 먼저 ./scripts/local_beta_setup.sh 를 실행하세요." >&2
    exit 1
}
require_cmd docker
require_cmd cloudflared
require_cmd claude
[[ -x "$AX_VENV_DIR/bin/celery" ]] || {
    echo "[start] ax-engine venv가 없습니다. ./scripts/local_beta_setup.sh 를 먼저 실행하세요." >&2
    exit 1
}
mkdir -p "$LOCAL_BETA_MEDIA_DIR/artifacts" "$LOCAL_BETA_MEDIA_DIR/slides" "$LOCAL_BETA_TMP_DIR"

# 이번 실행에서 새로 띄운 구성요소만 추적해, 실패 시 이번에 만든 부분만
# 되돌린다 — 이미 정상 동작 중이던 프로세스/컨테이너는 건드리지 않는다.
STARTED_WORKER=0
STARTED_TUNNEL=0
cleanup_on_failure() {
    local code=$?
    if [[ "$code" -ne 0 ]]; then
        echo "[start] 실패(exit $code) — 이번 실행에서 새로 띄운 구성요소만 정리합니다." >&2
        [[ "$STARTED_WORKER" -eq 1 ]] && stop_pidfile "$AX_WORKER_PID_FILE" "$AX_WORKER_SIGNATURE" "AX 워커"
        [[ "$STARTED_TUNNEL" -eq 1 ]] && stop_pidfile "$CLOUDFLARED_PID_FILE" "$CLOUDFLARED_SIGNATURE" "cloudflared"
        echo "[start] Docker 서비스는 유지했습니다. 상태 확인: ./scripts/local_beta_status.sh" >&2
    fi
}
trap cleanup_on_failure EXIT

compose config --quiet

wait_healthy() {
    local service="$1" timeout="${2:-120}" waited=0 cid status
    cid="$(compose ps -q "$service")"
    [[ -n "$cid" ]] || { echo "[start] $service 컨테이너를 찾을 수 없습니다." >&2; return 1; }
    while ((waited < timeout)); do
        status="$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")"
        [[ "$status" == "healthy" ]] && return 0
        if [[ "$status" == "unhealthy" ]]; then
            echo "[start] $service 가 unhealthy 상태입니다. 로그: docker compose -p $PROJECT_NAME logs $service" >&2
            return 1
        fi
        sleep 3
        waited=$((waited + 3))
    done
    echo "[start] $service 가 ${timeout}s 안에 healthy가 되지 않았습니다." >&2
    return 1
}

# postgres/redis를 먼저 올리고 healthy를 기다린 뒤에만 마이그레이션을 적용한다.
# 완전히 빈 DB에서 backend-web(gunicorn)/backend-worker/backend-beat를 먼저
# 띄우면 테이블이 없는 채로 요청을 받아 애플리케이션 레벨에서 깨진다.
compose up -d postgres redis

for service in postgres redis; do
    echo "[start] $service healthcheck 대기 중..."
    wait_healthy "$service"
done

# backend 이미지는 여기서 처음 필요해지므로(최초 실행 시 아직 빌드되지 않았을 수
# 있음), `compose run`이 필요하면 자동으로 빌드한 뒤 마이그레이션을 정확히 한 번만
# 실행한다. 이후 `up -d`가 같은 이미지를 재사용해 backend-web/worker/beat를 띄운다.
echo "[start] DB 마이그레이션 적용 중..."
compose run --rm --no-deps backend-web python manage.py migrate --noinput

compose up -d backend-web backend-worker backend-beat nginx

for service in backend-web backend-worker backend-beat nginx; do
    echo "[start] $service healthcheck 대기 중..."
    wait_healthy "$service"
done

if pidfile_is_running "$AX_WORKER_PID_FILE" "$AX_WORKER_SIGNATURE"; then
    echo "[start] AX 워커가 이미 실행 중입니다 (PID $(cat "$AX_WORKER_PID_FILE"))"
else
    redis_port="$(env_value LOCAL_BETA_REDIS_PORT)"
    (
        cd "$REPO_ROOT/ax-engine"
        export REDIS_URL="redis://127.0.0.1:${redis_port:-6380}/0"
        export ARTIFACT_DIR="$LOCAL_BETA_MEDIA_DIR/artifacts"
        export SLIDE_DIR="$LOCAL_BETA_MEDIA_DIR/slides"
        export TMPDIR="$LOCAL_BETA_TMP_DIR"
        export LLM_PROVIDER="claude_cli"
        export CLAUDE_CLI_TIMEOUT="$(env_value CLAUDE_CLI_TIMEOUT)"
        export CLAUDE_CLI_MODEL="$(env_value CLAUDE_CLI_MODEL)"
        nohup "$AX_VENV_DIR/bin/celery" -A celery_app worker -Q ax --loglevel=info --concurrency=2 \
            >>"$AX_WORKER_LOG_FILE" 2>&1 &
        echo $! >"$AX_WORKER_PID_FILE"
    )
    STARTED_WORKER=1
    sleep 1
    pidfile_is_running "$AX_WORKER_PID_FILE" "$AX_WORKER_SIGNATURE" || {
        echo "[start] AX 워커 기동 실패. 로그: $AX_WORKER_LOG_FILE" >&2
        exit 1
    }
    echo "[start] AX 워커 시작됨 (PID $(cat "$AX_WORKER_PID_FILE")), 로그: $AX_WORKER_LOG_FILE"
fi

if pidfile_is_running "$CLOUDFLARED_PID_FILE" "$CLOUDFLARED_SIGNATURE"; then
    tunnel_url="$(cat "$CLOUDFLARED_URL_FILE" 2>/dev/null || true)"
    echo "[start] cloudflared 가 이미 실행 중입니다 (PID $(cat "$CLOUDFLARED_PID_FILE"))"
else
    http_port="$(env_value BETA_HTTP_PORT)"
    : >"$CLOUDFLARED_LOG_FILE"
    nohup cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${http_port:-8080}" \
        >>"$CLOUDFLARED_LOG_FILE" 2>&1 &
    echo $! >"$CLOUDFLARED_PID_FILE"
    STARTED_TUNNEL=1

    tunnel_url=""
    for _ in $(seq 1 30); do
        tunnel_url="$(grep -Eo 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$CLOUDFLARED_LOG_FILE" | head -n1 || true)"
        [[ -n "$tunnel_url" ]] && break
        pidfile_is_running "$CLOUDFLARED_PID_FILE" "$CLOUDFLARED_SIGNATURE" || {
            echo "[start] cloudflared 가 예기치 않게 종료됐습니다. 로그: $CLOUDFLARED_LOG_FILE" >&2
            exit 1
        }
        sleep 1
    done
    [[ -n "$tunnel_url" ]] || {
        echo "[start] cloudflared Quick Tunnel URL을 ${30}s 안에 찾지 못했습니다. 로그: $CLOUDFLARED_LOG_FILE" >&2
        exit 1
    }
    echo "$tunnel_url" >"$CLOUDFLARED_URL_FILE"
    echo "[start] cloudflared 시작됨 (PID $(cat "$CLOUDFLARED_PID_FILE")): $tunnel_url"
fi

if [[ -n "${tunnel_url:-}" ]]; then
    echo "[start] 중요: Google Cloud Console → OAuth 2.0 클라이언트 → '승인된 자바스크립트 원본'에 다음 URL을 반드시 추가하세요: $tunnel_url"
    echo "[start] Quick Tunnel URL은 재시작할 때마다 바뀝니다 — 이전에 등록해 둔 origin은 재시작 후 더 이상 유효하지 않으니 매번 새 URL로 갱신하세요."
fi

trap - EXIT
echo "[start] 완료. 상태 확인: ./scripts/local_beta_status.sh"
