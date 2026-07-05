# Office-AX AX Engine (Celery 'ax' 큐 워커)
#
# 시스템 의존성:
#   - libreoffice    : PPTX 슬라이드 / DOCX 페이지 렌더링 (soffice headless)
#   - poppler-utils  : PDF → PNG 변환 (pdftoppm)
#   - fonts-noto-cjk : 한글 문서 렌더링 폰트
#
# OCR 스택(easyocr 등)은 베타 미지원 결정에 따라 설치하지 않는다
# (closed-beta-launch-plan-v1-ko.md 갭 6).
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress libreoffice-writer \
        poppler-utils \
        fonts-noto-cjk \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

# ax 큐 전용 워커 — Django 워커('celery' 큐)와 물리적으로 분리
CMD ["celery", "-A", "celery_app", "worker", "-Q", "ax", "--loglevel=info", "--concurrency=2"]
