#!/usr/bin/env bash
# 로컬 CLI QA 스택 상태 조회. 아무 것도 바꾸지 않는다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local_beta_common.sh
source "$SCRIPT_DIR/local_beta_common.sh"

echo "=== Docker Compose (${PROJECT_NAME}) ==="
if [[ -f "$ENV_FILE" ]]; then
    compose ps
else
    echo "[status] $ENV_FILE 이 없습니다 — ./scripts/local_beta_setup.sh 를 먼저 실행하세요." >&2
fi

echo
echo "=== 호스트 AX 워커 (claude_cli) ==="
if pidfile_is_running "$AX_WORKER_PID_FILE" "$AX_WORKER_SIGNATURE"; then
    echo "실행 중 (PID $(cat "$AX_WORKER_PID_FILE")), 로그: $AX_WORKER_LOG_FILE"
else
    echo "중지됨"
fi

echo
echo "=== cloudflared Quick Tunnel ==="
if pidfile_is_running "$CLOUDFLARED_PID_FILE" "$CLOUDFLARED_SIGNATURE"; then
    echo "실행 중 (PID $(cat "$CLOUDFLARED_PID_FILE"))"
    [[ -f "$CLOUDFLARED_URL_FILE" ]] && echo "URL: $(cat "$CLOUDFLARED_URL_FILE")"
else
    echo "중지됨"
fi

echo
echo "=== 경로 계약 ==="
echo "LOCAL_BETA_MEDIA_DIR=$LOCAL_BETA_MEDIA_DIR"
echo "LOCAL_BETA_TMP_DIR=$LOCAL_BETA_TMP_DIR"
if [[ -f "$ENV_FILE" ]]; then
    echo "BETA_ACCESS_MODE=$(env_value BETA_ACCESS_MODE)"
fi
