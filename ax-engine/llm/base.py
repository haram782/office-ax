from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    summary: str
    detected_errors: list[str] = field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    # LLM이 생성한 보정 파일 절대 경로 (없으면 빈 문자열)
    artifact_path: str = ""


class BaseLLMClient(ABC):
    """
    LLM 공급자 교체 시 이 인터페이스만 구현하면 된다.
    tasks/analyze_document.py는 이 클래스만 참조하므로 상위 레이어 변경 불필요.

    context 키 예시 (구현체에서 선택적으로 활용):
      source_type: "excel" | "pdf_digital" | "pdf_image"
      upload_id: int
    """

    @abstractmethod
    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        ...
