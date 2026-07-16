#!/usr/bin/env bash
# 로컬 CLI QA 스택 정지. 여러 번 실행해도 안전하다 — 이미 멈춰 있으면 그냥 넘어간다.
# 기본은 컨테이너만 멈추고 볼륨은 보존한다. 데이터까지 지우려면 --purge.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local_beta_common.sh
source "$SCRIPT_DIR/local_beta_common.sh"

PURGE=0
while (($#)); do
    case "$1" in
        --purge) PURGE=1; shift ;;
        *) echo "[stop] 알 수 없는 인자: $1" >&2; exit 2 ;;
    esac
done

stop_pidfile "$CLOUDFLARED_PID_FILE" "$CLOUDFLARED_SIGNATURE" "cloudflared"
rm -f "$CLOUDFLARED_URL_FILE"
stop_pidfile "$AX_WORKER_PID_FILE" "$AX_WORKER_SIGNATURE" "AX 워커"

if [[ -f "$ENV_FILE" ]]; then
    if [[ "$PURGE" -eq 1 ]]; then
        compose down -v --remove-orphans
        echo "[stop] Docker 컨테이너와 볼륨을 모두 제거했습니다."
    else
        compose stop
        echo "[stop] Docker 컨테이너를 멈췄습니다 (볼륨 보존). 완전 초기화는 --purge."
    fi
else
    echo "[stop] $ENV_FILE 이 없어 Docker 단계는 건너뜁니다."
fi

echo "[stop] 완료"
