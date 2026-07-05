# Office-AX backend (Django + Celery worker/beat 공용 이미지)
#
# 빌드 컨텍스트는 repo 루트여야 한다 (docker-compose.beta.yml 참조):
#   - backend/ 코드 외에 HWP Node 워커가 frontend/node_modules/@rhwp/core를
#     상대 경로로 임포트하므로 /app/frontend/node_modules 경로를 이미지 안에 재현한다.
#
# 시스템 의존성:
#   - nodejs 22          : HWP 텍스트 치환 워커 (backend/workers/hwp_worker.mjs)
#   - libreoffice        : PPTX 셰이프 패치 후 슬라이드 재렌더링 (pptx_render.py)
#   - poppler-utils      : PDF → PNG 변환 (pdftoppm)
#   - fonts-noto-cjk     : 한글 문서 렌더링 폰트
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# nodesource 22 — 개발 환경(node 22)과 동일 메이저 버전으로 WASM 워커 호환성 유지
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends \
        nodejs \
        libreoffice-impress libreoffice-writer \
        poppler-utils \
        fonts-noto-cjk \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 레이어 캐시 — 코드보다 먼저 복사
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# HWP 워커가 임포트하는 @rhwp/core를 frontend/node_modules 경로에 설치
# (frontend/package.json의 ^0.7.15와 동일 버전 고정)
RUN mkdir -p /app/frontend \
    && npm install --prefix /app/frontend --no-save @rhwp/core@0.7.15

COPY backend/ /app/backend/

WORKDIR /app/backend

# 기본 커맨드는 web — worker/beat는 compose에서 command 오버라이드
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "180"]
