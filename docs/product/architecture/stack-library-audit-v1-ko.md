# Office-AX 스택 및 라이브러리 감사 v1

문서 상태: 현재 아키텍처 판단 문서. 라이브러리 교체, 외부 런타임 도입, LLM gateway 전환, 문서 포맷 처리 전략을 바꾸기 전에 이 문서를 우선 확인한다.

## 1. 목적

이 문서는 Office-AX가 현재 사용하는 주요 라이브러리와 런타임을 정리하고, MVP 기준에서 유지할 것과 후속 POC가 필요한 것을 나눈다.

현재 제품의 핵심 목표는 "문서를 프롬프트로 수정하고, 검증 가능한 변경 제안과 실제 수정본 artifact를 남기는 것"이다.

따라서 라이브러리 판단 기준도 일반적인 문서 편집기 완성도가 아니라 다음에 맞춘다.

- 프롬프트 기반 patch plan을 실제 파일에 안정적으로 적용할 수 있는가
- 한국 업무 문서 흐름에 필요한 XLSX, HWP, PDF를 어느 정도 다룰 수 있는가
- LLM 호출, 사용량, 비용을 추적할 수 있는가
- 배포와 운영 난도가 MVP 범위를 넘지 않는가
- 라이선스가 B2B SaaS에 부담이 되지 않는가

## 2. 결론 요약

MVP에서는 큰 스택 교체를 하지 않는다.

권장 방향:

```text
XLSX        → openpyxl 유지
PDF viewer  → pdfjs-dist 유지
PDF patcher → PyMuPDF 유지, replace_text는 별도 POC
HWP         → @rhwp/core 유지, 표/양식은 별도 POC
DOCX/PPTX   → 현재 라이브러리는 제한 지원, 고충실도는 LibreOffice/OnlyOffice 계열 후속 검토
LLM         → 로컬 CLI/직접 client 유지, UsageEvent 이후 LiteLLM류 gateway 검토
Queue       → Celery + Redis 유지
Frontend    → React hooks 유지, polling/cache 복잡도 증가 시 TanStack Query 검토
```

지금 필요한 것은 교체가 아니라 경계선이다.

- 현재 스택으로 닫을 MVP 범위
- POC 후 결정할 범위
- MVP에서 과한 범위

## 3. 현재 사용 스택

### 3.1 Frontend

현재 주요 라이브러리:

- React 18
- Vite 5
- Tailwind CSS
- axios
- pdfjs-dist
- @rhwp/core
- mammoth
- docx-preview
- react-router-dom
- Vitest / Testing Library

역할:

- React/Vite/Tailwind: 제품 UI
- pdfjs-dist: PDF canvas viewer
- @rhwp/core: HWP 브라우저 렌더/파싱 계열
- mammoth/docx-preview: DOCX 텍스트/미리보기 보조
- axios: REST API client

판단:

현재 MVP에는 충분하다.

다만 채팅, 버전, patch status, dashboard polling이 늘어나면 React hook 내부 수동 polling이 점점 복잡해진다. 이 시점에는 TanStack Query 같은 server state 도구를 검토할 수 있다.

MVP에서는 도입하지 않는다.

### 3.2 Backend

현재 주요 라이브러리:

- Django 5
- Django REST Framework
- Celery + Redis
- openpyxl
- pandas
- python-docx
- python-pptx
- PyMuPDF
- requests
- anthropic
- psycopg2-binary

역할:

- Django/DRF: 인증, API, 모델, 관리자 도구
- Celery/Redis: 분석, PatchPlan 생성, patcher 실행
- openpyxl: XLSX patcher
- python-docx/python-pptx: DOCX/PPTX 제한적 patcher/분석
- PyMuPDF: PDF annotate/redact_overlay patcher
- pandas: 일부 표 데이터 처리

판단:

현재 구조는 MVP에 맞다.

문서 수정 제품의 핵심 상태인 `DocumentChange`, `DocumentVersion`, artifact 저장, apply/reject API가 Django 모델과 잘 맞는다.

Celery는 지금처럼 짧은 비동기 작업에는 충분하다. 단, 장기적으로 반복 파이프라인, 재시도 정책, 작업 그래프, 외부 이벤트 연동이 커지면 Temporal, Prefect, Dagster 같은 workflow engine을 별도 검토할 수 있다.

MVP에서는 Celery를 유지한다.

### 3.3 AX Engine

현재 주요 라이브러리:

- Celery + Redis
- openpyxl
- pandas
- pypdf
- python-docx
- python-pptx
- Pillow
- olefile
- openai
- anthropic
- python-dotenv

역할:

- LLM 호출
- 문서 분석
- PDF 텍스트 추출
- DOCX/PPTX/HWP 보조 파싱
- PatchPlan 생성

판단:

AX Engine은 "문서 분석/LLM 호출"과 "파일 patching"의 경계가 섞이지 않게 유지해야 한다.

현재 방향처럼 LLM은 PatchPlan을 만들고, 실제 파일 수정은 Django backend patcher가 담당하는 구조가 맞다.

## 4. 포맷별 라이브러리 판단

### 4.1 XLSX

현재:

- openpyxl

현재 지원 또는 진행된 범위:

- `replace_cell`
- `set_cell_style`
- `set_number_format`
- `set_formula`

판단:

openpyxl 유지.

openpyxl은 XLSX/XLSM 계열 파일을 Python에서 읽고 쓰는 목적에 잘 맞는다. 현재 MVP의 핵심인 셀 값, 스타일, 표시 형식, 수식 설정에는 충분하다.

주의:

- openpyxl은 Excel 계산 엔진이 아니다.
- 수식 값을 계산하지 않는다.
- 복잡한 차트, 피벗, 매크로, 외부 연결은 보존/검증이 제한적일 수 있다.

후속 보강 후보:

- LibreOffice headless: 수식 재계산, 렌더링 검증, PDF 변환 확인
- Excel COM/Graph API: Windows/Office 종속성이 커서 MVP 제외

결론:

MVP에서 XLSX는 openpyxl 중심으로 계속 간다.

### 4.2 PDF viewer

현재:

- pdfjs-dist

역할:

- PDF canvas 렌더링
- 페이지 이동
- zoom
- `pdf_bbox` highlight overlay

판단:

유지.

브라우저 내 PDF 보기와 하이라이트 overlay에는 pdfjs-dist가 가장 현실적이다.

주의:

- pdfjs-dist는 viewer이지 patcher가 아니다.
- 텍스트 레이어와 selection 기반 하이라이트가 필요해지면 현재 canvas viewer 위에 text layer를 추가하는 POC가 필요하다.

결론:

MVP에서는 유지한다.

### 4.3 PDF patcher

현재:

- PyMuPDF

현재 지원:

- `annotate`
- `redact_overlay`

현재 미지원:

- `replace_text`
- 구조 수정
- 표/양식 재배치
- 스캔 PDF OCR 기반 수정

판단:

PyMuPDF 유지.

PyMuPDF는 PDF 페이지 수정, 주석, redaction, 텍스트 삽입을 직접 지원하므로 현재 patcher 역할에 가장 가깝다.

다만 PDF의 `replace_text`는 단순 문자열 치환이 아니다.

필요한 단계:

```text
원문 텍스트 탐색
  → 정확한 rect/quad 확보
  → 원문 redaction
  → 한글 폰트로 replacement 삽입
  → 줄바꿈/박스 overflow 검증
  → 추출 텍스트와 시각 결과 확인
```

후속 POC 후보:

- PyMuPDF `search_for` + `add_redact_annot(text=..., fontname="korea-s")`
- PyMuPDF `search_for` + `apply_redactions` + `insert_textbox`
- pdfplumber로 텍스트/테이블 좌표 분석 보조

주의:

- PyMuPDF 라이선스는 별도 확인이 필요하다.
- B2B SaaS 배포에서는 AGPL/상용 라이선스 영향을 검토해야 한다.
- 한글, 다국어, 폰트 임베딩, viewer별 렌더링 차이를 회귀 테스트로 고정해야 한다.

결론:

MVP에서는 PDF를 `annotate`/`redact_overlay` 제한 지원으로 유지하고, `replace_text`는 `pdf-replace-text-poc`로 분리한다.

### 4.4 PDF 분석 보조

현재:

- AX Engine: pypdf
- pdfplumber 미사용

판단:

pypdf는 단순 텍스트 추출과 PDF 조작 일부에는 유용하지만, Office-AX의 PDF patcher 중심 엔진은 아니다.

pdfplumber는 텍스트/좌표/테이블 분석과 visual debugging에 강하지만 PDF 수정은 제공하지 않는다.

결론:

pdfplumber는 patcher 대체가 아니라 분석 보조 후보로 둔다.

### 4.5 HWP

현재:

- @rhwp/core
- backend Node worker

판단:

유지.

HWP는 대체 가능한 오픈소스 선택지가 많지 않다. 현재처럼 @rhwp/core를 중심으로 제한적 텍스트 치환을 안정화하는 방향이 맞다.

주의:

- 표/양식 수정은 현재 MVP 범위를 넘는다.
- Node worker의 메모리, timeout, 브라우저 전역 객체 의존성은 계속 감시해야 한다.
- HWP export가 안정적으로 되는지 샘플 기반 회귀 테스트가 필요하다.

결론:

MVP에서는 HWP를 "제한적 텍스트 처리"로 표현한다. 표/양식 수정은 별도 POC 이후 결정한다.

### 4.6 DOCX

현재:

- python-docx
- mammoth
- docx-preview
- LibreOffice headless 계열 변환 코드

판단:

현재 라이브러리는 제한 지원에 적합하다.

- python-docx: 문단, run, 표 셀 수준 조작 가능
- mammoth: DOCX → HTML/text 추출에 유용
- docx-preview: 브라우저 미리보기 보조
- LibreOffice headless: 페이지 이미지/PDF 변환으로 고충실도 preview 보조

주의:

- DOCX는 스타일, run 분할, 표, section, header/footer가 복잡하다.
- "공무체로 바꿔줘" 같은 재작성은 patch보다 regenerate에 가깝다.

결론:

MVP에서는 DOCX 정식 수정 지원을 하지 않는다. 후속으로 "표 셀 텍스트 변경" 같은 좁은 operation부터 검토한다.

### 4.7 PPTX

현재:

- python-pptx
- LibreOffice/pdftoppm 계열 렌더링

판단:

제한 지원.

PPTX는 slide shape, text frame, table, image, theme, layout이 얽혀 있어 patch 범위가 넓다.

결론:

MVP에서는 PPTX 정식 수정 지원을 미룬다. preview와 검토 중심으로 둔다.

## 5. Office 고충실도 환경 후보

### 5.1 LibreOffice headless

현재:

- DOCX/PPTX 렌더링 계열 코드에서 외부 런타임으로 사용된다.

강점:

- self-host 가능
- DOCX/PPTX/XLSX/PDF 변환에 실용적
- 수식 재계산이나 렌더링 검증 보조 가능

약점:

- 서버 설치/버전 관리 필요
- 결과물이 MS Office와 100% 동일하지 않을 수 있음
- 병렬 처리와 timeout 관리 필요

판단:

MVP 보조 런타임으로 유지 가능하다.

단, 배포 문서에 LibreOffice, poppler/pdftoppm 같은 외부 바이너리 의존성을 명시해야 한다.

### 5.2 ONLYOFFICE Docs / Document Builder

후보:

- 웹 기반 Office viewer/editor
- 문서 변환
- Document Builder
- WOPI/API 통합

강점:

- DOCX/XLSX/PPTX 고충실도 편집/렌더링에 강함
- 브라우저 안에서 익숙한 Office UI 제공
- API/WOPI 통합 가능

약점:

- Office-AX의 "프롬프트 기반 patcher" 모델과 제품 방향이 달라질 수 있음
- 배포, 라이선스, 운영 비용이 큼
- 사용자 직접 편집기로 제품이 보일 위험이 있음

판단:

지금 도입하지 않는다.

향후 다음 조건 중 하나가 생기면 POC한다.

- DOCX/PPTX 고충실도 viewer가 핵심 경쟁력이 된다.
- 사용자가 브라우저 안에서 직접 Office 문서를 보면서 검토해야 한다.
- patcher보다 Office editor API를 이용하는 것이 더 안전한 작업이 많아진다.

### 5.3 상용 PDF SDK

후보:

- Apryse/PDFTron 계열
- Adobe PDF Services 계열
- 기타 PDF SDK

강점:

- PDF 편집, redaction, form, 변환, 뷰어까지 넓게 지원
- 엔터프라이즈 지원 가능

약점:

- 비용과 라이선스 부담
- self-host/데이터 보안/국내 문서 처리 정책 검토 필요
- MVP에는 과함

판단:

PDF가 핵심 과금 기능이 되기 전까지 도입하지 않는다.

## 6. LLM 호출 및 사용량 추적

현재:

- 로컬 CLI 기반 Gemini/Claude 계열 개발 경로
- openai/anthropic 직접 client
- AX Engine task 기반 호출

문제:

- provider별 응답 형식이 다르다.
- 로컬 CLI는 token usage를 안정적으로 주지 않을 수 있다.
- 비용 추적, retry, fallback, rate limit, observability가 흩어진다.

MVP 방향:

1. 먼저 `UsageEvent`를 자체 모델로 만든다.
2. 현재 client/CLI 호출 결과를 UsageEvent로 기록한다.
3. token usage가 없으면 추정값을 저장한다.
4. 모델별 단가는 설정 스냅샷으로 계산한다.
5. 이후 LiteLLM 같은 gateway 도입 여부를 검토한다.

LiteLLM류 gateway 장점:

- 여러 provider를 단일 API로 묶기 쉬움
- fallback/routing/budget/spend tracking 기능과 방향성이 맞음
- UsageEvent 설계와 연결하기 좋음

도입 보류 이유:

- 지금은 로컬 CLI 개발 흐름이 중요하다.
- gateway를 먼저 붙이면 디버깅 지점이 하나 늘어난다.
- 제품 핵심 루프가 안정화된 뒤 붙이는 것이 낫다.

결론:

MVP 다음 작업은 LLM gateway 도입이 아니라 `UsageEvent`와 호출 계측이다.

## 7. 프론트엔드 상태 관리

현재:

- React hook 기반 local/server state 혼합
- axios API client
- 수동 polling

판단:

MVP에는 충분하다.

다만 다음이 늘어나면 TanStack Query 같은 server state 도구를 검토한다.

- 채팅 메시지 polling
- 버전 생성 polling
- dashboard usage polling
- document changes refetch
- optimistic update rollback

도입 기준:

```text
동일 API의 refetch/polling/cache/invalidation 로직이 3곳 이상 중복되면 검토
```

MVP에서는 지금 구조를 유지한다.

## 8. 보안/라이선스 체크포인트

스택 교체보다 먼저 확인할 항목:

- PyMuPDF 라이선스와 SaaS 배포 영향
- ONLYOFFICE / 상용 PDF SDK 도입 시 라이선스 비용
- LibreOffice headless 서버 배포 라이선스/패키징
- 업로드 문서 보관/삭제 정책
- LLM provider로 문서 내용이 전달되는 범위
- 로컬 CLI 개발 경로와 production API 경로의 분리

## 9. 의사결정 매트릭스

| 영역 | 현재 | MVP 판단 | 후속 후보 |
|---|---|---|---|
| XLSX patcher | openpyxl | 유지 | LibreOffice 재계산/렌더 검증 |
| PDF viewer | pdfjs-dist | 유지 | text layer POC |
| PDF patcher | PyMuPDF | 유지, 제한 지원 | pdfplumber 보조, 상용 SDK 검토 |
| HWP | @rhwp/core | 유지, 제한 지원 | 표/양식 POC |
| DOCX | python-docx/mammoth/docx-preview | 제한 지원 | LibreOffice/ONLYOFFICE POC |
| PPTX | python-pptx/LibreOffice render | 제한 지원 | ONLYOFFICE POC |
| LLM | local CLI/direct client | 유지 | UsageEvent 후 LiteLLM 검토 |
| Queue | Celery + Redis | 유지 | workflow engine 후속 |
| Frontend state | React hooks | 유지 | TanStack Query 후속 |

## 10. 다음 POC 후보

우선순위:

1. `pdf-replace-text-poc`
   - PyMuPDF로 한글 replace_text가 실제로 가능한지 검증
   - `search_for`, `redact_annot`, `insert_textbox`, `fontname="korea-s"` 비교

2. `usage-event-metering`
   - LLM 호출별 provider/model/token/latency/status 기록
   - 로컬 CLI token 추정

3. `hwp-table-api-poc`
   - @rhwp/core로 표 셀 탐색과 수정 가능성 확인

4. `office-high-fidelity-viewer-poc`
   - ONLYOFFICE 또는 LibreOffice 변환 기반 viewer가 Office-AX UX에 맞는지 확인

## 11. 한 줄 결론

Office-AX는 지금 라이브러리를 크게 교체할 단계가 아니다. XLSX happy path와 UsageEvent 계측은 현재 스택으로 닫고, PDF replace_text, HWP 표/양식, Office 고충실도 viewer, LLM gateway만 별도 POC로 분리해 판단한다.

## 12. 참고 링크

- openpyxl: https://openpyxl.readthedocs.io/en/stable/
- PyMuPDF Page API: https://pymupdf.readthedocs.io/en/latest/page.html
- pdfplumber: https://github.com/jsvine/pdfplumber
- pypdf: https://pypdf.readthedocs.io/
- ONLYOFFICE Developer Edition: https://www.onlyoffice.com/developer-edition
- LiteLLM: https://docs.litellm.ai/docs/
