"""Keyword evaluator (Layer 2) — exact term matching and semantic similarity checks."""

import logging
import math

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
)

logger = logging.getLogger(__name__)

_SEMANTIC_PASS_THRESHOLD = 0.70
_SEMANTIC_FAIL_THRESHOLD = 0.40


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float vectors using pure Python.

    Returns:
        Similarity score in [0.0, 1.0], or 0.0 if either vector has zero norm.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class KeywordEvaluator:
    """Layer 2 evaluator checking required_terms — forbidden, exact, and semantic.

    Checks are applied in order: forbidden → exact → semantic. The first terminal
    verdict stops the pipeline. If required_terms is absent or empty, short-circuits
    to UNKNOWN to allow downstream layers to continue.
    """

    def __init__(self, *, embedding_service: EmbeddingProviderApi) -> None:
        self._embedding_service = embedding_service

    @property
    def layer(self) -> EvalLayer:
        """Return the evaluation layer identifier."""
        return EvalLayer.KEYWORD

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult:
        """Evaluate required term constraints against the model response.

        Args:
            task: The benchmark task containing required_terms constraints.
            result: The benchmark result containing the model's response.

        Returns:
            Terminal FAIL if a constraint is violated; terminal PASS if semantic
            threshold met; non-terminal UNKNOWN otherwise.
        """
        rt = task.required_terms
        if rt is None or (not rt.exact and not rt.semantic and not rt.forbidden):
            return self._unknown("No required terms configured")

        response = (result.sanitized_response or result.raw_response or "").lower()

        forbidden_result = self._check_forbidden(rt.forbidden, response)
        if forbidden_result is not None:
            return forbidden_result

        exact_result = self._check_exact(rt.exact, response)
        if exact_result is not None:
            return exact_result

        if rt.semantic:
            return self._check_semantic(rt.semantic, result.sanitized_response or result.raw_response or "")

        return self._unknown("Exact terms matched; no semantic check configured")

    def _check_forbidden(self, forbidden: tuple[str, ...], response_lower: str) -> EvaluationResult | None:
        found = tuple(t for t in forbidden if t.lower() in response_lower)
        if found:
            return EvaluationResult(
                verdict=EvalVerdict.FAIL,
                score=0.0,
                reasoning=f"Forbidden term found: '{found[0]}'",
                is_terminal=True,
                layer=self.layer,
                found_forbidden_terms=found,
            )
        return None

    def _check_exact(self, exact: tuple[str, ...], response_lower: str) -> EvaluationResult | None:
        missing = tuple(t for t in exact if t.lower() not in response_lower)
        if missing:
            return EvaluationResult(
                verdict=EvalVerdict.FAIL,
                score=0.0,
                reasoning=f"Missing required terms: {list(missing)}",
                is_terminal=True,
                layer=self.layer,
                missing_exact_terms=missing,
            )
        return None

    def _check_semantic(self, semantic_terms: tuple[str, ...], response_text: str) -> EvaluationResult:
        try:
            embeddings = self._embedding_service.encode([response_text, *semantic_terms])
        except Exception:
            logger.warning("keyword_semantic_encode_failed", extra={"terms": list(semantic_terms)})
            return self._unknown("Semantic check skipped: embedding error")

        response_vec = embeddings[0]
        term_vecs = embeddings[1:]
        if not term_vecs:
            return self._unknown("No term embeddings returned")

        scores = tuple(_cosine_similarity(tv, response_vec) for tv in term_vecs)
        avg_sim = sum(scores) / len(scores)

        if avg_sim >= _SEMANTIC_PASS_THRESHOLD:
            return EvaluationResult(
                verdict=EvalVerdict.PASS,
                score=avg_sim,
                reasoning=f"Semantic similarity {avg_sim:.3f} >= {_SEMANTIC_PASS_THRESHOLD}",
                is_terminal=True,
                layer=self.layer,
                semantic_term_scores=scores,
            )
        if avg_sim < _SEMANTIC_FAIL_THRESHOLD:
            return EvaluationResult(
                verdict=EvalVerdict.FAIL,
                score=0.0,
                reasoning=f"Semantic similarity {avg_sim:.3f} < {_SEMANTIC_FAIL_THRESHOLD}",
                is_terminal=True,
                layer=self.layer,
                semantic_term_scores=scores,
            )
        return EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning=f"Semantic similarity {avg_sim:.3f} between thresholds",
            is_terminal=False,
            layer=self.layer,
            semantic_term_scores=scores,
        )

    def _unknown(self, reasoning: str) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning=reasoning,
            is_terminal=False,
            layer=self.layer,
        )
