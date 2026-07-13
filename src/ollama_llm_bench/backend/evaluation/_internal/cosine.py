"""The cosine phase: whole-text cosine similarity against the golden answer (§6.4 of
04_EVALUATION_PIPELINE.md)."""

from ollama_llm_bench.backend.domain import Verdict
from ollama_llm_bench.backend.embedding import EmbeddingService
from ollama_llm_bench.backend.evaluation.models import CosinePhaseResult


class _CosineEvaluatorImpl:
    """The concrete cosine-phase evaluator; never constructed outside ``api.py``."""

    def __init__(self, *, embedding_service: EmbeddingService) -> None:
        self._embedding_service = embedding_service

    def evaluate(
        self, *, response: str, golden_answer: str | None, cosine_enabled: bool
    ) -> CosinePhaseResult:
        if not cosine_enabled or not golden_answer:
            return CosinePhaseResult(verdict=None, similarity=None)

        similarity = self._embedding_service.cosine(text_a=response, text_b=golden_answer)
        threshold = self._embedding_service.cosine_threshold()
        verdict = Verdict.PASS if similarity >= threshold else Verdict.FAIL
        return CosinePhaseResult(verdict=verdict, similarity=similarity)
