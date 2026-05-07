"""Cosine similarity evaluator (Layer 3) — response vs golden_answer embedding comparison."""

import logging
import math

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
    ResponseScope,
    TaskType,
)

logger = logging.getLogger(__name__)

_SKIP_TASK_TYPES: frozenset[TaskType] = frozenset(
    {
        TaskType.CODE_GENERATION,
        TaskType.CODE_REVIEW,
        TaskType.REASONING,
    }
)

_SCOPE_THRESHOLDS: dict[ResponseScope, tuple[float, float]] = {
    ResponseScope.EXACT: (0.92, 0.30),
    ResponseScope.CONTAINS: (0.85, 0.25),
    ResponseScope.COVERS: (0.75, 0.20),
}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float vectors using pure Python.

    Returns:
        Similarity score in [0.0, 1.0], or 0.0 if either vector has zero norm.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class CosineSimilarityEvaluator:
    """Layer 3 evaluator comparing response embedding to golden_answer via cosine similarity.

    Skips evaluation for CODE_GENERATION, CODE_REVIEW, and REASONING task types,
    returning non-terminal UNKNOWN to allow Layer 4 to continue. For all other types,
    encodes golden_answer and the response in a single batch call, computes cosine
    similarity, and maps the result to a terminal verdict using response_scope thresholds.

    Thresholds (pass_threshold, fail_threshold) by ResponseScope:
        EXACT:    (0.92, 0.30)
        CONTAINS: (0.85, 0.25)
        COVERS:   (0.75, 0.20)
    """

    def __init__(self, *, embedding_service: EmbeddingProviderApi) -> None:
        self._embedding_service = embedding_service

    @property
    def layer(self) -> EvalLayer:
        """Return the evaluation layer identifier."""
        return EvalLayer.COSINE

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult:
        """Compare response to golden_answer via cosine similarity and return a verdict.

        Args:
            task: Benchmark task with golden_answer and response_scope fields.
            result: Benchmark result with the model's response text.

        Returns:
            Non-terminal UNKNOWN for skipped task types or embedding errors; terminal
            PASS, FAIL, or non-terminal UNKNOWN based on scope thresholds otherwise.
        """
        response = result.sanitized_response or result.raw_response or ""

        if task.task_type in _SKIP_TASK_TYPES:
            return self._unknown(f"Cosine skipped for {task.task_type}")

        ok, similarity = self._compute_similarity(task.golden_answer, response)
        if not ok:
            return self._unknown("Cosine skipped: embedding error")

        scope = task.response_scope if task.response_scope is not None else ResponseScope.CONTAINS
        pass_t, fail_t = _SCOPE_THRESHOLDS[scope]

        if similarity >= pass_t:
            return self._pass(similarity, scope)
        if similarity < fail_t:
            return self._fail(similarity, scope)
        return self._unknown(f"Cosine {similarity:.3f} between thresholds for {scope}")

    def _compute_similarity(self, golden: str, response: str) -> tuple[bool, float]:
        try:
            vecs = self._embedding_service.encode([golden, response])
            sim = _cosine_similarity(vecs[0], vecs[1])
            return True, sim
        except Exception:
            logger.warning("cosine_encode_failed", extra={"golden_len": len(golden), "response_len": len(response)})
            return False, 0.0

    def _pass(self, similarity: float, scope: ResponseScope) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.PASS,
            score=similarity,
            reasoning=f"Cosine {similarity:.3f} >= {_SCOPE_THRESHOLDS[scope][0]} ({scope})",
            is_terminal=True,
            layer=self.layer,
        )

    def _fail(self, similarity: float, scope: ResponseScope) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.FAIL,
            score=0.0,
            reasoning=f"Cosine {similarity:.3f} < {_SCOPE_THRESHOLDS[scope][1]} ({scope})",
            is_terminal=True,
            layer=self.layer,
        )

    def _unknown(self, reasoning: str) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning=reasoning,
            is_terminal=False,
            layer=self.layer,
        )
