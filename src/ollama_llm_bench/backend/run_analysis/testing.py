"""A fake ``RunAnalysisService`` for downstream consumers' tests."""

from ollama_llm_bench.backend.domain import ModelName, ProviderId, RunId
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome, RunAnalysisResult

__all__: list[str] = ["FakeRunAnalysisService"]


class FakeRunAnalysisService:
    """Records every ``generate()`` call and returns a canned, settable result."""

    def __init__(self) -> None:
        self.calls: list[tuple[RunId, ProviderId, ModelName]] = []
        self.next_result: RunAnalysisResult = RunAnalysisResult(
            outcome=RunAnalysisOutcome.GENERATED, run_analysis_markdown="## Overview\n\nfake"
        )

    def generate(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> RunAnalysisResult:
        """Record the call and return ``self.next_result`` (mutate it between calls)."""
        self.calls.append((run_id, provider_id, model_name))
        return self.next_result
