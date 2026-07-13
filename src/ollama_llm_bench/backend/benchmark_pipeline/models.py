"""Domain DTOs and enums owned by the benchmark pipeline."""

from enum import StrEnum
from typing import Final


class Phase(StrEnum):
    """The five-phase batched pipeline's fixed stage sequence (08-B §3)."""

    INITIALIZATION = "initialization"
    INFERENCE = "inference"
    KEYWORD_CHECK = "keyword_check"
    COSINE_CHECK = "cosine_check"
    JUDGE_CHECK = "judge_check"


PHASE_ORDER: Final[tuple[Phase, ...]] = (
    Phase.INITIALIZATION,
    Phase.INFERENCE,
    Phase.KEYWORD_CHECK,
    Phase.COSINE_CHECK,
    Phase.JUDGE_CHECK,
)
"""The five phases in the strict, never-reordered order the pipeline executes them (08-B §3)."""
