# 로컬 CLI QA 런북 (single-Mac, host claude_cli)

이 문서는 단일 Mac에서 Docker(postgres/redis/backend-web/backend-worker/backend-beat/nginx)와
호스트 AX Celery 워커(`claude_cli`)를 함께 띄워, `cloudflared` Quick Tunnel로 Google 로그인이
가능한 임시 HTTPS URL을 통해 QA하는 절차다. 운영 `docker-compose.beta.yml` / `.env.beta` /
`scripts/beta_*.sh`는 이 절차에서 전혀 사용하지 않는다.

## 0. 구성 개요

- Docker: `postgres`, `redis`, `backend-web`, `backend-worker`, `backend-beat`, `nginx`.
  `ax-worker` 컨테이너는 `container-ax` profile 뒤에 숨겨져 있어 기본 기동에서 빠진다.
- 호스트(macOS): AX Celery 워커(`ax-engine`, 큐 `ax`)가 `claude` CLI를 subprocess로 호출한다.
- `cloudflared tunnel --url http://127.0.0.1:$BETA_HTTP_PORT` Quick Tunnel이 nginx를 외부에 노출한다.
- 경로 계약: `backend-web`/`backend-worker`가 파일 절대경로를 Redis 큐로 넘겨 호스트 AX 워커가
  그대로 읽고 쓴다. 그래서 `LOCAL_BETA_MEDIA_DIR`/`LOCAL_BETA_TMP_DIR`는 컨테이너 안에서도
  **호스트와 동일한 절대경로**로 bind mount된다(`docker-compose.local-beta.yml`의
  `source == target`). 두 값은 `scripts/local_beta_common.sh` 한 곳에서만 파생되며 기본값은
  `<repo>/.local-beta/media`, `<repo>/.local-beta/tmp`다.
- BETA 게이트: `.env.local-beta.example`은 `BETA_ACCESS_MODE=open`이 기본값이다. Google 로그인은
  그대로 유지되고, 이메일 allowlist만 해제되어 인증된 계정을 모두 허용한다(계정별 격리는
  기존 모델 그대로 유지).

## 1. 최초 준비

```bash
./scripts/local_beta_setup.sh
```

- 필요한 실행 파일(`docker`, `cloudflared`, `claude`, `python3`)이 없으면 설치 안내와 함께 중단한다.
- `.local-beta/media`, `.local-beta/media/artifacts`, `.local-beta/media/slides`, `.local-beta/tmp`를 만든다.
- `.env.local-beta`가 없으면 `.env.local-beta.example`을 복사해 생성한다(이미 있으면 건드리지 않는다 — idempotent).
  생성 직후 `DJANGO_SECRET_KEY`, `DB_PASSWORD`/`BETA_DB_PASSWORD`, `VITE_GOOGLE_CLIENT_ID`를 실제 값으로 채운다.
- `.local-beta/ax-venv`에 ax-engine 전용 Python venv를 만들고(이미 있으면 재사용) `ax-engine/requirements.txt`를 설치한다.

여러 번 실행해도 안전하다. `.env.local-beta`와 `.local-beta/`는 `.gitignore`에 등록되어 있다.

## 2. 기동

```bash
./scripts/local_beta_start.sh
```

순서:

1. `docker compose config --quiet`로 병합 설정을 검증한다.
2. `postgres redis backend-web backend-worker backend-beat nginx`만 `up -d` 한다(`ax-worker` 제외).
3. 네 서비스(`backend-web`/`backend-worker`/`backend-beat`/`nginx`) healthcheck를 순서대로 대기한다.
4. 호스트 AX 워커가 이미 실행 중이 아니면(`pidfile` 서명 확인) `.local-beta/ax-venv`의 celery로
   `-A celery_app worker -Q ax`를 백그라운드로 띄우고 PID를 `.local-beta/ax-worker.pid`에 기록한다.
   `REDIS_URL`은 `127.0.0.1:${LOCAL_BETA_REDIS_PORT:-6380}`, `ARTIFACT_DIR`/`SLIDE_DIR`/`TMPDIR`은
   경로 계약과 동일한 절대경로를 쓴다.
5. `cloudflared`가 이미 실행 중이 아니면 Quick Tunnel을 새로 띄우고, 로그에서
   `https://*.trycloudflare.com` URL을 최대 30초 대기해 `.local-beta/cloudflared.url`에 기록한다.

이미 떠 있는 구성요소는 건드리지 않으므로 재실행해도 안전하다(idempotent). 이번 실행에서
새로 시작한 호스트 워커/터널이 도중에 실패하면, **이번에 새로 띄운 것만** 정리하고
(이미 정상이던 Docker 서비스는 그대로 둔 채) 실패 원인을 stderr에 남긴다.

## 3. 상태 확인

```bash
./scripts/local_beta_status.sh
```

`docker compose ps`, 호스트 AX 워커 PID/로그 경로, cloudflared PID/터널 URL,
`LOCAL_BETA_MEDIA_DIR`/`LOCAL_BETA_TMP_DIR`, 현재 `BETA_ACCESS_MODE`를 보여준다. 아무 것도 바꾸지 않는다.

## 4. QA 스모크

- `./scripts/local_beta_status.sh`로 얻은 `https://*.trycloudflare.com` URL로 브라우저 접속.
- Google 로그인 후 `BETA_ALLOWED_EMAILS` 목록과 무관하게(즉 `BETA_ACCESS_MODE=open`) 어떤
  Google 계정으로도 로그인이 되는지 확인한다. 다만 세션/문서/사용량은 계정별로 분리되는지
  (다른 계정 로그인 시 서로의 문서가 보이지 않는지) 반드시 확인한다.
- PDF/DOCX/PPTX/XLSX/HWP 업로드 → AI 교정 요청까지 진행해, 호스트 AX 워커 로그
  (`.local-beta/ax-worker.log`)에 `claude` CLI 호출이 찍히는지 확인한다.
- 절대경로 계약 확인: 업로드한 파일이 `.local-beta/media` 아래에 실제로 생기고, AX 워커가
  같은 경로에서 읽어 결과를 쓰는지 확인한다(경로가 어긋나면 AX 태스크가 FileNotFoundError로 실패한다).
- cloudflared 로그(`.local-beta/cloudflared.log`)나 nginx 로그에 5xx가 없는지 확인한다.

## 5. 정지

```bash
./scripts/local_beta_stop.sh          # 컨테이너만 정지, 볼륨(DB/media) 보존
./scripts/local_beta_stop.sh --purge  # 컨테이너+볼륨까지 완전 초기화
```

- cloudflared → 호스트 AX 워커 순으로 pidfile 서명을 확인한 뒤에만 종료한다(PID 재사용으로
  다른 프로세스를 잘못 죽이는 사고를 막기 위함). 이미 멈춰 있으면 조용히 넘어간다.
- 기본은 `docker compose stop`만 실행해 다음에 `local_beta_start.sh`로 이어서 QA할 수 있게 한다.
- `--purge`는 명시적으로 요청했을 때만 데이터까지 지운다.

## 6. 장애 대응

- `local_beta_start.sh`가 healthcheck 대기 중 실패하면 `docker compose -p officeax-local-beta logs <service>`로 원인을 본다.
- 호스트 AX 워커가 죽어 있으면 `.local-beta/ax-worker.log`를 확인한다. `claude` CLI 미인증/미설치가
  가장 흔한 원인이다(`claude` 명령이 대화형 로그인 상태인지 먼저 확인).
- cloudflared가 URL을 못 찾고 종료됐다면 `.local-beta/cloudflared.log`를 확인한다. 사내 방화벽이
  아웃바운드를 막는 경우가 흔하다.
- PID 재사용으로 pidfile이 의심스러우면(`stop`이 "서명이 일치하지 않아 건너뜁니다" 로그를 남긴 경우)
  `ps -p $(cat .local-beta/ax-worker.pid)` 등으로 직접 확인한 뒤 필요하면 수동으로 종료한다.
- BETA 게이트 오동작(전체 공개가 아니거나 반대로 아무도 못 들어오는 경우): `.env.local-beta`의
  `BETA_ACCESS_MODE` 오타 여부를 확인한다. `backend/apps/accounts/views.py`의 `_is_beta_allowed`는
  `open`/`allowlist`/미설정 외의 값은 fail-closed(403)로 처리한다.
