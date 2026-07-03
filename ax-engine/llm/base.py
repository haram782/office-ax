from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    summary: str
    detected_errors: list[str] = field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    # LLM 공급자 식별자 ("anthropic" | "openai" | "gemini" 등) — backend UsageEvent 기록용
    provider: str = ""
    # 토큰 수 출처: provider가 실제 반환한 값인지, 텍스트 길이로 추정한 값인지 구분
    token_source: str = "provider_reported"
    # LLM이 생성한 보정 파일 절대 경로 (없으면 빈 문자열)
    artifact_path: str = ""
    # LLM 응답 전체 파싱 결과 — 의도 판별 등 summary 외 필드가 필요한 경우 사용
    parsed_data: dict = field(default_factory=dict)


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
