#!/usr/bin/env bash
# 로컬 CLI QA 최초 준비. 여러 번 실행해도 안전하다(idempotent) —
# 이미 존재하는 파일/디렉터리/venv는 건드리지 않는다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local_beta_common.sh
source "$SCRIPT_DIR/local_beta_common.sh"

AX_PYTHON_BIN="${AX_PYTHON_BIN:-python3}"
missing_cmd=0
for cmd in docker cloudflared claude "$AX_PYTHON_BIN"; do
    require_cmd "$cmd" || missing_cmd=1
done
if [[ "$missing_cmd" -ne 0 ]]; then
    cat >&2 <<'EOF'
[local-beta] 위 실행 파일을 먼저 설치하세요.
  docker      : Docker Desktop
  cloudflared : brew install cloudflared
  claude      : Claude Code CLI (https://claude.ai/code)
  python3     : ax-engine 호스트 워커 venv 구성에 필요
EOF
    exit 1
fi

mkdir -p "$STATE_DIR" "$LOCAL_BETA_MEDIA_DIR/artifacts" "$LOCAL_BETA_MEDIA_DIR/slides" "$LOCAL_BETA_TMP_DIR"
echo "[setup] 공유 경로 준비 완료"
echo "  LOCAL_BETA_MEDIA_DIR=$LOCAL_BETA_MEDIA_DIR"
echo "  LOCAL_BETA_TMP_DIR=$LOCAL_BETA_TMP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    require_file "$REPO_ROOT/.env.local-beta.example"
    cp "$REPO_ROOT/.env.local-beta.example" "$ENV_FILE"
    echo "[setup] $ENV_FILE 생성됨 — DJANGO_SECRET_KEY, DB 비밀번호, VITE_GOOGLE_CLIENT_ID를 채우세요."
else
    echo "[setup] $ENV_FILE 이미 있어 유지합니다."
fi

if [[ ! -x "$AX_VENV_DIR/bin/python" ]]; then
    "$AX_PYTHON_BIN" -m venv "$AX_VENV_DIR"
    echo "[setup] ax-engine venv 생성됨: $AX_VENV_DIR"
fi
"$AX_VENV_DIR/bin/pip" install --quiet --upgrade pip
"$AX_VENV_DIR/bin/pip" install --quiet -r "$REPO_ROOT/ax-engine/requirements.txt"
echo "[setup] ax-engine 의존성 설치/갱신 완료"

echo "[setup] 완료. ./scripts/local_beta_start.sh 로 스택을 올리세요."
