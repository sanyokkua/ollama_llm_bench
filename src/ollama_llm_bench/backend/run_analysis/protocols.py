"""The ``RunAnalysisService`` contract (§2.1, `08-E` §17)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import ModelName, ProviderId, RunId
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisResult

__all__: list[str] = ["RunAnalysisService"]


class RunAnalysisService(Protocol):
    """Generate the single consolidated run-analysis narrative for a run."""

    def generate(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> RunAnalysisResult:
        """blocking; invoked on a ``TaskRunner``/``QThreadPool`` worker thread (D-R-01).

        Loads the run, results, and tasks internally; aggregates a bounded digest;
        builds a mode-aware prompt; calls the analysis model at most once. Never
        raises for a call failure — every failure mode is captured into the
        returned ``RunAnalysisResult`` (``outcome=FAILED``). Never persists anything;
        the caller applies the result via a ``RunStatusPatch``.

        Args:
            run_id: The run to analyze; must be in a terminal status.
            provider_id: The chosen analysis provider.
            model_name: The chosen analysis model.

        Returns:
            The outcome of this invocation.

        Raises:
            ContractViolationError: ``run_id`` names a run not in a terminal status
                (``COMPLETED``/``STOPPED``/``FAILED``) — a programmer-error precondition
                violation; the UI must never invoke this while a run is active.
        """
        ...
