# office-ax

HWP 서식의 빈칸을 말 한마디로 채우는 사무 문서 AI입니다.

새 도구를 배우게 하지 않고, 사람들이 원래 쓰는 문서(HWP) 안으로 AI를 가져가는 것이 목표입니다.
혼자 진행한 개인 프로젝트이며 **미완성**입니다. 구현의 상당 부분은 AI 코딩 에이전트(Claude Code, Codex)가 했습니다.

## 동작

1. HWP를 올리고 "소유자 성명(상호) 칸에 '박하람'을 넣어줘"처럼 요청합니다.
2. LLM이 문서 구조를 읽고 어느 라벨 옆 칸에 무엇을 넣을지 **수정 제안(PatchPlan)** 을 만듭니다.
3. 사용자가 제안을 확인하고 반영하면, 원본 서식은 그대로 두고 값만 넣은 새 버전이 생깁니다.

HWP 수정은 `ax-engine/`의 PatchPlan 생성과 `@rhwp/core`(WASM) 기반 HWP 워커가 맡습니다.

## 구성

| 경로 | 역할 |
|---|---|
| `frontend/` | React 웹 워크스페이스 (문서 미리보기, 수정 제안, 대화) |
| `backend/` | Django REST API, 업로드·버전·수정 제안 저장, Celery 작업 |
| `ax-engine/` | LLM 호출과 문서 처리를 맡는 Celery 워커 (큐 `ax`) |
| `infra/`, `docker-compose*.yml` | 로컬·베타 실행 환경 |
| `scripts/` | 평가 스크립트와 평가 기록 |

## 실행

단일 Mac에서 Docker와 호스트 AX 워커로 띄우는 절차는 [docs/operations/local-beta-cli-qa-runbook.md](docs/operations/local-beta-cli-qa-runbook.md)에 있습니다.

## 평가 기록

처음 평가와 이후 재평가의 결과가 다릅니다. 둘 다 그대로 남겨 둡니다.

| 기록 | 기준 | 결과 |
|---|---|---|
| [scripts/EVAL_RESULTS.md](scripts/EVAL_RESULTS.md) | 개발 중 쓴 문서 10케이스, "적용됐나" | 10/10 |
| [scripts/AIGEN_STRICT_EVAL_NEW_DOCS_RECORD.md](scripts/AIGEN_STRICT_EVAL_NEW_DOCS_RECORD.md) | 처음 보는 법령 서식 5개, "맞는 칸에 들어갔나" (1회 실행) | **2/5** |
| [scripts/AIGEN_E2E_POA_RECORD.md](scripts/AIGEN_E2E_POA_RECORD.md) | 위임장 시연 1건 | 기록상 성공 → 렌더링 확인 결과 **실패** (문서 맨 위 정정 참고) |

실패 3건은 원인이 같았습니다. 라벨 셀이 colSpan으로 넓게 펼쳐진 서식에서, 가장 가까운 빈 셀을 찾는 로직이 멀리 떨어진 장식용 빈 행을 골랐습니다.
결과 파일을 그림으로 그려 보면 값이 1~3px 크기로 무관한 행에 들어가 있었고, 성공한 경우는 12~17px로 정상 표시됐습니다.
