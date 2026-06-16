import os
import time
import uuid
from pathlib import Path

from .base import BaseLLMClient, AnalysisResult

# source_type별 mock 응답 정의
_MOCK_RESPONSES: dict[str, dict] = {
    "xlsx": {
        "summary": (
            "1월 매출 집계 데이터로 총 32개 항목이 확인되었습니다.\n"
            "D열 '단가' 항목에서 음수값 3건이 감지되어 검토가 필요합니다.\n"
            "전체 합계 셀(B34)이 수식 오류(#REF!) 상태로 즉시 수정을 권장합니다."
        ),
        "errors": [
            "D12: 단가 음수값 (-15,000) — 입력 오류 의심",
            "D27: 단가 음수값 (-3,200) — 입력 오류 의심",
            "D31: 단가 음수값 (-500) — 입력 오류 의심",
            "B34: 합계 수식 오류 (#REF!) — 참조 범위 깨짐",
        ],
        "make_artifact": True,
    },
    "csv": {
        "summary": (
            "CSV 데이터 파일 분석 완료. 총 47개 레코드가 확인되었습니다.\n"
            "날짜 컬럼에서 형식 불일치 2건, 금액 컬럼에서 이상값 1건이 감지되었습니다."
        ),
        "errors": [
            "3행: 날짜 형식 오류 (2024/01/15 → 2024-01-15)",
            "19행: 날짜 형식 오류 (15-Jan-2024 → 2024-01-15)",
            "28행: 금액 이상값 (999999999 — 검토 필요)",
        ],
        "make_artifact": False,
    },
    "pdf_digital": {
        "summary": (
            "3페이지 분량의 계약서입니다.\n"
            "계약 기간, 지급 조건, 당사자 정보가 포함되어 있습니다.\n"
            "개인정보(주민등록번호, 연락처) 마스킹이 적용되었습니다."
        ),
        "errors": [
            "p.2: 계약 종료일이 시작일보다 앞서 있음 — 날짜 확인 필요",
        ],
        "make_artifact": False,
    },
    "pdf_image": {
        "summary": (
            "스캔 이미지 PDF에서 OCR로 텍스트를 추출했습니다.\n"
            "문서 품질에 따라 인식 정확도가 낮을 수 있습니다."
        ),
        "errors": [
            "인식 신뢰도 낮은 텍스트 영역 발견 — 수동 확인 권장",
        ],
        "make_artifact": False,
    },
    "docx": {
        "summary": (
            "Word 문서 분석 완료. 총 8개 단락, 2개 표가 확인되었습니다.\n"
            "맞춤법 오류 3건과 표 서식 불일치 1건이 감지되었습니다."
        ),
        "errors": [
            "p.1: 맞춤법 오류 — '되요' → '돼요'",
            "p.3: 맞춤법 오류 — '않되' → '안 돼'",
            "p.5: 맞춤법 오류 — '왠만하면' → '웬만하면'",
            "표 1: 첫 행 헤더 서식 미적용",
        ],
        "make_artifact": False,
    },
    "pptx": {
        "summary": (
            "프레젠테이션 12슬라이드 분석 완료.\n"
            "슬라이드 4, 7에서 텍스트 오버플로우가 감지되었습니다.\n"
            "일관성 없는 글꼴이 3개 슬라이드에서 발견되었습니다."
        ),
        "errors": [
            "슬라이드 4: 텍스트 박스 오버플로우 — 내용 줄임 또는 폰트 크기 조정 권장",
            "슬라이드 7: 텍스트 박스 오버플로우",
            "슬라이드 2, 5, 9: 글꼴 혼용 (맑은고딕/굴림/Arial)",
        ],
        "make_artifact": False,
    },
    "hwp": {
        "summary": (
            "한글 문서(.hwp) 분석 완료.\n"
            "공문서 형식의 2페이지 문서로, 주요 항목 검토 결과를 제공합니다."
        ),
        "errors": [
            "본문 날짜 표기 형식 불일치 — 'YYYY년 MM월 DD일' 통일 권장",
        ],
        "make_artifact": False,
    },
    "image": {
        "summary": (
            "이미지에서 OCR로 텍스트를 추출했습니다.\n"
            "영수증 또는 문서 스캔본으로 판단됩니다."
        ),
        "errors": [
            "일부 텍스트 영역 인식 불가 — 이미지 해상도 향상 권장",
        ],
        "make_artifact": False,
    },
}

_DEFAULT_RESPONSE = {
    "summary": "문서 분석이 완료되었습니다.",
    "errors": [],
    "make_artifact": False,
}


class MockLLMClient(BaseLLMClient):
    """
    외부 API 호출 없이 3초 후 포맷별 가짜 분석 결과를 반환하는 로컬 테스트용 클라이언트.
    source_type == "xlsx" 일 때 보정된 가짜 Excel 파일을 ARTIFACT_DIR에 생성한다.
    """

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        time.sleep(3)

        source_type = context.get("source_type", "unknown")
        mock = _MOCK_RESPONSES.get(source_type, _DEFAULT_RESPONSE)

        artifact_path = ""
        if mock.get("make_artifact"):
            artifact_path = self._create_corrected_excel()

        return AnalysisResult(
            summary=mock["summary"],
            detected_errors=mock["errors"],
            model_used="mock-v1",
            input_tokens=0,
            output_tokens=0,
            artifact_path=artifact_path,
        )

    def _create_corrected_excel(self) -> str:
        """보정된 샘플 엑셀 파일을 생성하고 절대 경로를 반환한다."""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            return ""

        artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "/tmp/ax-artifacts"))
        artifact_dir.mkdir(parents=True, exist_ok=True)

        filename = f"corrected_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = artifact_dir / filename

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "보정된 매출 집계"

        headers = ["날짜", "품목", "수량", "단가", "합계"]
        header_style = {"bold": True, "fill": PatternFill(fill_type="solid", fgColor="D9E1F2")}
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = header_style["fill"]

        rows = [
            ("2024-01-03", "사무용품A", 10, 15000, "=C2*D2"),
            ("2024-01-10", "사무용품B", 5,  3200,  "=C3*D3"),
            ("2024-01-17", "사무용품C", 20, 500,   "=C4*D4"),
            ("2024-01-24", "사무용품D", 8,  8800,  "=C5*D5"),
        ]
        for row_idx, row_data in enumerate(rows, 2):
            for col_idx, val in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=val)

        last_row = len(rows) + 1
        ws.cell(row=last_row + 1, column=4, value="합계")
        ws.cell(row=last_row + 1, column=5, value=f"=SUM(E2:E{last_row})")

        ws.cell(
            row=last_row + 3,
            column=1,
            value="[AI 보정 완료] 음수 단가 3건 → 절댓값 수정 / #REF! 수식 → =SUM(E2:E5) 복원",
        )

        wb.save(file_path)
        return str(file_path)
