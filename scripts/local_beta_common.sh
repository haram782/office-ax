#!/usr/bin/env bash
# 로컬 CLI QA 입력은 docker-compose.beta.yml + docker-compose.local-beta.yml,
# .env.local-beta, --project-directory로 고정한다. 운영 beta_common.sh는 건드리지 않는다.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILES=(-f "$REPO_ROOT/docker-compose.beta.yml" -f "$REPO_ROOT/docker-compose.local-beta.yml")
ENV_FILE="${BETA_ENV_FILE:-$REPO_ROOT/.env.local-beta}"
export BETA_ENV_FILE="$ENV_FILE"
PROJECT_NAME="officeax-local-beta"

# Docker(backend-web/backend-worker)와 호스트 AX 워커가 완전히 같은 절대경로를
# 봐야 하므로(경로 계약), 값을 여기 한 곳에서만 파생시켜 모든 로컬 QA 스크립트가
# 공유한다. 사용자가 직접 값을 넣게 하면 두 쪽이 어긋날 위험이 있어 고정한다.
STATE_DIR="$REPO_ROOT/.local-beta"
LOCAL_BETA_MEDIA_DIR="${LOCAL_BETA_MEDIA_DIR:-$STATE_DIR/media}"
LOCAL_BETA_TMP_DIR="${LOCAL_BETA_TMP_DIR:-$STATE_DIR/tmp}"
export LOCAL_BETA_MEDIA_DIR LOCAL_BETA_TMP_DIR

AX_VENV_DIR="$STATE_DIR/ax-venv"
AX_WORKER_PID_FILE="$STATE_DIR/ax-worker.pid"
AX_WORKER_LOG_FILE="$STATE_DIR/ax-worker.log"
# stop/status가 pidfile의 PID를 우리가 띄운 celery 프로세스로 확인할 때 쓰는
# 커맨드라인 서명. start에서 실제로 실행하는 커맨드와 반드시 일치해야 한다.
AX_WORKER_SIGNATURE="$AX_VENV_DIR/bin/celery -A celery_app worker -Q ax"
CLOUDFLARED_PID_FILE="$STATE_DIR/cloudflared.pid"
CLOUDFLARED_LOG_FILE="$STATE_DIR/cloudflared.log"
CLOUDFLARED_URL_FILE="$STATE_DIR/cloudflared.url"
CLOUDFLARED_SIGNATURE="cloudflared tunnel"

compose() {
    docker compose -p "$PROJECT_NAME" "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" --project-directory "$REPO_ROOT" "$@"
}

env_value() {
    local key="$1"
    awk -F= -v key="$key" '$0 !~ /^[[:space:]]*#/ && $1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

require_file() {
    if [[ ! -f "$1" ]]; then
        echo "[local-beta] 필수 파일이 없습니다: $1" >&2
        return 1
    fi
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "[local-beta] 필요한 실행 파일을 찾을 수 없습니다: $1" >&2
        return 1
    }
}

# pidfile에 적힌 PID가 실제로 우리가 띄운 프로세스인지 커맨드라인 서명으로
# 확인한다. PID 재사용으로 무관한 프로세스를 오인해 종료하는 사고를 막는다.
#
# fork() 직후 execve()가 아직 끝나지 않은 아주 짧은 구간에 ps가 그 PID를
# 스냅샷하면, 자식 프로세스가 아직 부모의 이전 커맨드라인(예: python3)으로
# 보여 서명이 일치하지 않는 것처럼 보일 수 있다. 이 구간은 보통 무시할 수
# 있을 만큼 짧지만, 샌드박스처럼 시스템콜 오버헤드가 큰 환경에서는 길어져
# "process signature matching is environment-dependent" 오탐(false negative)
# 으로 이어질 수 있다. 짧게 재시도해 이 창을 흡수하되, PID가 살아있는 동안만
# 재시도하고 최종적으로 서명이 일치하지 않으면 그대로 실패시켜 PID 재사용
# 방지 효과는 그대로 유지한다.
pid_matches_signature() {
    local pid="$1" signature="$2" cmdline attempt
    [[ -n "$pid" ]] || return 1
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    for attempt in $(seq 1 20); do
        # -ww: 비 tty(예: 사이드카/캡처 파이프)에서 커맨드라인이 폭 제한으로
        # 잘리는 것을 막는다. command= 키워드를 지원하지 않는 ps 구현을 위해
        # args=로 한 번 더 시도한다.
        cmdline="$(ps -ww -p "$pid" -o command= 2>/dev/null || true)"
        [[ -n "$cmdline" ]] || cmdline="$(ps -ww -p "$pid" -o args= 2>/dev/null || true)"
        if [[ -n "$cmdline" && "$cmdline" == *"$signature"* ]]; then
            return 0
        fi
        kill -0 "$pid" 2>/dev/null || return 1
        sleep 0.05
    done
    return 1
}

# pidfile 기준으로 안전 종료한다. 이미 없거나 서명이 다르면 조용히 건너뛰어
# 재실행(idempotent)해도 오류가 나지 않는다.
stop_pidfile() {
    local pidfile="$1" signature="$2" label="$3" pid
    [[ -f "$pidfile" ]] || return 0
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if pid_matches_signature "$pid" "$signature"; then
        kill "$pid" 2>/dev/null || true
        local waited=0
        while kill -0 "$pid" 2>/dev/null && ((waited < 10)); do
            sleep 0.5
            waited=$((waited + 1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "[local-beta] $label PID $pid 가 정상 종료되지 않아 강제 종료합니다." >&2
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "[local-beta] $label 중지됨 (PID $pid)"
    elif [[ -n "$pid" ]]; then
        echo "[local-beta] $label pidfile($pidfile)의 PID $pid 서명이 일치하지 않아 건너뜁니다." >&2
    fi
    rm -f "$pidfile"
}

pidfile_is_running() {
    local pidfile="$1" signature="$2" pid
    [[ -f "$pidfile" ]] || return 1
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    pid_matches_signature "$pid" "$signature"
}
