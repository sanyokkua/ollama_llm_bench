"""DTOs produced by the four evaluation phases (04_EVALUATION_PIPELINE.md §6;
08-P_judge_protocol.md §10)."""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResultTerm,
    CosineScore,
    DurationMs,
    NonNegativeInt,
    ResolutionLayer,
    Verdict,
)

__all__: list[str] = [
    "CombinedVerdict",
    "CosinePhaseResult",
    "JudgePhaseOutcome",
    "JudgePhaseResult",
    "KeywordPhaseResult",
]


class KeywordPhaseResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The keyword phase's outcome for one result (§6.3)."""

    verdict: Verdict
    terms: tuple[BenchmarkResultTerm, ...]


class CosinePhaseResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The cosine phase's outcome for one result (§6.4).

    Both fields are ``None`` when the phase was skipped for the task
    (``cosine_enabled: false`` or no ``golden_answer`` — DD-46).
    """

    verdict: Verdict | None
    similarity: CosineScore | None


class JudgePhaseOutcome(StrEnum):
    """How the judge phase concluded for one result (§9, §11.4 of
    08-P_judge_protocol.md)."""

    RESOLVED = "resolved"
    TRANSPORT_FAILURE = "transport_failure"
    PARSE_EXHAUSTED = "parse_exhausted"


class JudgePhaseResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The judge phase's outcome for one result (§10 of 08-P_judge_protocol.md)."""

    outcome: JudgePhaseOutcome
    verdict: Verdict | None
    reasoning: str
    time_ms: DurationMs
    completion_tokens: NonNegativeInt | None


class CombinedVerdict(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The final combined verdict and the layer that decided it (§6.6 / §11)."""

    verdict: Verdict
    resolution_layer: ResolutionLayer
