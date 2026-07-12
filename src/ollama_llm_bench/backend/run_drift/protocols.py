"""RunDriftDetector — this module's swap point (spec §1, §6)."""

from typing import Protocol

from ollama_llm_bench.backend.run_drift.models import DriftWarning, RunDriftDetectionInputs

__all__: list[str] = ["RunDriftDetector"]


class RunDriftDetector(Protocol):
    """Compare a run's frozen snapshot to the live environment (spec §1)."""

    def detect(self, inputs: RunDriftDetectionInputs, /) -> tuple[DriftWarning, ...]:
        """Fast, synchronous, pure, idempotent; never raises (spec §8, §9).

        Returns:
            An ordered, possibly empty tuple of DriftWarning items (spec §3, §6.5).
        """
        ...
