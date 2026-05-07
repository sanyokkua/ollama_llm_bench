"""Rule-based evaluator (Layer 1) — fast deterministic checks for obviously failing responses."""

import logging

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
)

logger = logging.getLogger(__name__)

_MIN_RESPONSE_CHARS = 10
_ERROR_MARKERS = frozenset(
    {
        "error:",
        "traceback (most recent call last)",
        "exception:",
        "syntaxerror",
        "nameerror",
        "typeerror",
        "fatal error",
    }
)


class RuleBasedEvaluator:
    """Layer 1 evaluator applying fast, deterministic rules to detect failing responses.

    Checks are applied in order; the first failing check returns a terminal FAIL result,
    short-circuiting the remaining evaluation pipeline. If all checks pass, returns
    UNKNOWN with is_terminal=False to allow downstream layers to continue evaluation.
    """

    def __init__(self) -> None:
        pass

    @property
    def layer(self) -> EvalLayer:
        """Return the evaluation layer identifier."""
        return EvalLayer.RULE_BASED

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult:
        """Apply rule-based checks in order and return the first failing result.

        Args:
            task: The benchmark task containing the original question.
            result: The benchmark result containing the model's response.

        Returns:
            Terminal FAIL if any check fails; non-terminal UNKNOWN if all pass.
        """
        response = (result.sanitized_response or result.raw_response or "").strip()

        if result.has_inference_error:
            return self._fail(f"Inference error: {result.inference_error_message}")
        if not response:
            return self._fail("Response is empty")
        if response.lower().startswith(task.question.lower().strip()[:100]):
            return self._fail("Response echoes the input prompt")
        if len(response) < _MIN_RESPONSE_CHARS:
            return self._fail(f"Response too short ({len(response)} chars)")
        if any(marker in response.lower() for marker in _ERROR_MARKERS):
            return self._fail("Response contains error marker")

        return EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning="All rule-based checks passed",
            is_terminal=False,
            layer=self.layer,
        )

    def _fail(self, reasoning: str) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.FAIL,
            score=0.0,
            reasoning=reasoning,
            is_terminal=True,
            layer=self.layer,
        )
