#!/usr/bin/env bash
# 테스트 전용 가짜 docker 실행기 — 실제 컨테이너를 띄우지 않고 beta_backup.sh/beta_restore.sh가
# 호출하는 `docker compose ...` 하위 명령을 흉내낸다. 호출 인자는 FAKE_DOCKER_LOG에 기록되어
# 테스트가 writer 재시작, destructive 단계 도달 여부를 검증할 수 있게 한다.
set -uo pipefail

args="$*"
: "${FAKE_DOCKER_LOG:?FAKE_DOCKER_LOG must be set}"
printf '%s\n' "$args" >>"$FAKE_DOCKER_LOG"

# 파이프 상류가 남긴 stdin을 비워 SIGPIPE로 상위 명령이 이상 종료하지 않게 한다.
drain_stdin() {
    cat >/dev/null 2>&1 || true
}

if [[ -n "${FAKE_DOCKER_FAIL:-}" && "$args" == *"$FAKE_DOCKER_FAIL"* ]]; then
    echo "fake-docker: forced failure matching [$FAKE_DOCKER_FAIL]" >&2
    drain_stdin
    exit 7
fi

case "$args" in
    *"ps --status running --services"*)
        printf '%s\n' "${FAKE_DOCKER_RUNNING_SERVICES:-backend-web
backend-worker
backend-beat
ax-worker}"
        ;;
    *"pg_dump"*)
        printf 'FAKE-SQL-DUMP\n'
        ;;
    *"tar -C /app/backend/media -czf - ."*)
        tmpd="$(mktemp -d)"
        printf 'fake-media' >"$tmpd/file.txt"
        if [[ -n "${FAKE_MEDIA_TAR_SYMLINK:-}" ]]; then
            ln -s /etc/passwd "$tmpd/evil-link"
        fi
        # macOS bsdtar의 -czf는 gzip 스트림을 여러 member로 나눠 써서
        # `gzip -t`/`-dc`가 "trailing garbage"로 오판할 수 있다.
        # tar와 gzip을 분리 파이프해 단일 gzip member로 만든다.
        tar -cf - -C "$tmpd" . | gzip -9
        rm -rf "$tmpd"
        ;;
    *"showmigrations --plan"*)
        printf '[X] 0001_initial\n'
        ;;
    *psql*|*"tar -C /app/backend/media -xf -"*)
        drain_stdin
        ;;
    *)
        drain_stdin
        ;;
esac
exit 0
