"""Protocols for the four evaluation phases (04_EVALUATION_PIPELINE.md §6;
08-P_judge_protocol.md)."""

from typing import Protocol

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import BenchmarkTask, DurationMs, RequiredTerms
from ollama_llm_bench.backend.evaluation.models import (
    CosinePhaseResult,
    JudgePhaseResult,
    KeywordPhaseResult,
)

__all__: list[str] = [
    "CosineEvaluator",
    "JudgeEvaluator",
    "KeywordEvaluator",
    "SanityChecker",
]


class SanityChecker(Protocol):
    """The deterministic sanity pre-check (§6.2). No model call, no I/O."""

    def check(self, *, response: str, task: BenchmarkTask) -> bool:
        """Decide whether ``response`` is a plausible answer to ``task``.

        fast-synchronous; callable from any context. Never raises.

        Args:
            response: The candidate ``sanitized_response`` text.
            task: The frozen task; only ``question``, ``task_origin``, and
                the caller's snapshot-derived thresholds are consulted.

        Returns:
            ``sanity_check_passed`` — ``True`` when the response is plausible.
        """
        ...


class KeywordEvaluator(Protocol):
    """The keyword phase (§6.3): exact / forbidden / semantic term matching."""

    def evaluate(self, *, response: str, required_terms: RequiredTerms) -> KeywordPhaseResult:
        """Grade ``response`` against a task's declared required terms.

        blocking — semantic terms call the injected ``EmbeddingService``.

        Args:
            response: The candidate ``sanitized_response`` text.
            required_terms: The task's exact/semantic/forbidden term lists.

        Returns:
            The binary ``keyword_verdict`` plus the per-term
            ``BenchmarkResultTerm`` rows.
        """
        ...


class CosineEvaluator(Protocol):
    """The cosine phase (§6.4): whole-text cosine similarity against the golden answer."""

    def evaluate(
        self, *, response: str, golden_answer: str | None, cosine_enabled: bool
    ) -> CosinePhaseResult:
        """Grade ``response`` against ``golden_answer`` by cosine similarity.

        blocking — delegates to the injected ``EmbeddingService``. Never
        raises; an embedding timeout/failure yields
        ``CosinePhaseResult(verdict=None, similarity=None)`` (D-012).

        Args:
            response: The candidate ``sanitized_response`` text.
            golden_answer: The task's reference answer, or ``None``.
            cosine_enabled: The task's own opt-out flag (DD-46).

        Returns:
            The cosine phase's outcome; both fields ``None`` when skipped.
        """
        ...


class JudgeEvaluator(Protocol):
    """The judge phase (08-P_judge_protocol.md): the LLM-as-judge grading call."""

    def evaluate(
        self,
        *,
        response: str,
        system_prompt_sent: str | None,
        task: BenchmarkTask,
        timeout_ms: DurationMs,
        token: CancellationToken,
    ) -> JudgePhaseResult:
        """Issue one judge call (with retries) grading ``response`` against ``task``.

        blocking; invoked on a worker thread. ``timeout_ms`` is the
        per-attempt budget the caller (the pipeline, via the Adaptive
        Timeout Service) has already computed; this evaluator does not
        compute its own budget. ``token`` is forwarded verbatim to the
        underlying ``LLMClient.chat`` call (ADR-0005's mandatory parameter)
        — this evaluator does not itself branch on cancellation state.

        Args:
            response: The candidate ``sanitized_response`` text (never
                ``raw_response``).
            system_prompt_sent: The system prompt the candidate model
                received for this result, or ``None``.
            task: The frozen task providing question/criteria/context.
            timeout_ms: The per-attempt call budget.
            token: The run's live ``CancellationToken``.

        Returns:
            The judge phase's outcome, never with a numeric score.

        Raises:
            ProviderContextLengthError: The assembled prompt exceeded the
                judge model's context window (DD-46 §4.3) — a permanent,
                non-retried error surfaced uncaught to the caller.
        """
        ...
