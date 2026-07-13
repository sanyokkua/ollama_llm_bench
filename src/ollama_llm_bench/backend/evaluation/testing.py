"""Fakes for the four evaluation-phase Protocols — for downstream consumers
(the benchmark-pipeline stories)."""

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkResultTerm,
    BenchmarkTask,
    CosineScore,
    DurationMs,
    Verdict,
)
from ollama_llm_bench.backend.evaluation.models import (
    CosinePhaseResult,
    JudgePhaseOutcome,
    JudgePhaseResult,
    KeywordPhaseResult,
)

__all__: list[str] = [
    "FakeCosineEvaluator",
    "FakeJudgeEvaluator",
    "FakeKeywordEvaluator",
    "FakeSanityChecker",
]


class FakeSanityChecker:
    """A canned ``SanityChecker`` stand-in; defaults to always passing."""

    def __init__(self, *, result: bool = True) -> None:
        self._result = result
        self.calls: list[str] = []

    def check(
        self,
        *,
        response: str,
        task: BenchmarkTask,  # noqa: ARG002  # canned fake: task unused by design
    ) -> bool:
        self.calls.append(response)
        return self._result


class FakeKeywordEvaluator:
    """A canned ``KeywordEvaluator`` stand-in; defaults to an empty PASS."""

    def __init__(
        self,
        *,
        verdict: Verdict = Verdict.PASS,
        terms: tuple[BenchmarkResultTerm, ...] = (),
    ) -> None:
        self._result = KeywordPhaseResult(verdict=verdict, terms=terms)
        self.calls: list[str] = []

    def evaluate(
        self,
        *,
        response: str,
        required_terms: object,  # noqa: ARG002  # canned fake: input unused by design
    ) -> KeywordPhaseResult:
        self.calls.append(response)
        return self._result


class FakeCosineEvaluator:
    """A canned ``CosineEvaluator`` stand-in; defaults to a skipped phase."""

    def __init__(
        self, *, verdict: Verdict | None = None, similarity: CosineScore | None = None
    ) -> None:
        self._result = CosinePhaseResult(verdict=verdict, similarity=similarity)
        self.calls: list[str] = []

    def evaluate(
        self,
        *,
        response: str,
        golden_answer: str | None,  # noqa: ARG002  # canned fake: input unused by design
        cosine_enabled: bool,  # noqa: ARG002  # canned fake: input unused by design
    ) -> CosinePhaseResult:
        self.calls.append(response)
        return self._result


class FakeJudgeEvaluator:
    """A canned ``JudgeEvaluator`` stand-in; defaults to a resolved PASS."""

    def __init__(
        self,
        *,
        outcome: JudgePhaseOutcome = JudgePhaseOutcome.RESOLVED,
        verdict: Verdict | None = Verdict.PASS,
        reasoning: str = "canned reasoning",
        time_ms: DurationMs = 0,
        completion_tokens: int | None = None,
    ) -> None:
        self._result = JudgePhaseResult(
            outcome=outcome,
            verdict=verdict,
            reasoning=reasoning,
            time_ms=time_ms,
            completion_tokens=completion_tokens,
        )
        self.calls: list[str] = []

    def evaluate(
        self,
        *,
        response: str,
        system_prompt_sent: str | None,  # noqa: ARG002  # canned fake: input unused by design
        task: BenchmarkTask,  # noqa: ARG002  # canned fake: input unused by design
        timeout_ms: DurationMs,  # noqa: ARG002  # canned fake: input unused by design
        token: CancellationToken,  # noqa: ARG002  # canned fake: input unused by design
    ) -> JudgePhaseResult:
        self.calls.append(response)
        return self._result
