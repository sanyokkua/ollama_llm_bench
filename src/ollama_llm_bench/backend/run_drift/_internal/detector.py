"""The concrete, stateless RunDriftDetector implementation (spec §6, §8, §9)."""

from ollama_llm_bench.backend.run_drift._internal import ordering
from ollama_llm_bench.backend.run_drift._internal.embedding_check import run_embedding_check
from ollama_llm_bench.backend.run_drift._internal.judge_check import run_judge_check
from ollama_llm_bench.backend.run_drift._internal.provider_check import run_provider_check
from ollama_llm_bench.backend.run_drift._internal.test_model_check import run_test_model_check
from ollama_llm_bench.backend.run_drift.models import (
    DriftKind,
    DriftSeverity,
    DriftWarning,
    RunDriftDetectionInputs,
)

__all__: list[str] = ["_RunDriftDetectorImpl"]

_INCOMPLETE_SNAPSHOT_HEADLINE = "Run snapshot is incomplete."
_INCOMPLETE_SNAPSHOT_DETAIL = "Run snapshot is incomplete"


class _RunDriftDetectorImpl:
    """Stateless, synchronous, pure implementation of ``RunDriftDetector`` (spec §6)."""

    def detect(self, inputs: RunDriftDetectionInputs, /) -> tuple[DriftWarning, ...]:
        """Run the four availability checks in order and assemble the result (spec §6, §8).

        Returns:
            An ordered, possibly empty tuple of DriftWarning items.
        """
        if not inputs.run.providers or not inputs.run.models:
            return (_incomplete_snapshot_warning(),)

        warnings: list[DriftWarning] = []
        provider_warnings, blocked_provider_ids = run_provider_check(
            run=inputs.run,
            live_providers=inputs.live_providers,
            readiness=inputs.readiness,
            process_environment=inputs.process_environment,
            resumable_results=inputs.resumable_results,
        )
        warnings.extend(provider_warnings)
        warnings.extend(
            run_test_model_check(
                run=inputs.run,
                live_models=inputs.live_models,
                blocked_provider_ids=blocked_provider_ids,
                resumable_results=inputs.resumable_results,
            )
        )
        warnings.extend(
            run_judge_check(
                run=inputs.run,
                live_models=inputs.live_models,
                blocked_provider_ids=blocked_provider_ids,
                resumable_results=inputs.resumable_results,
            )
        )
        warnings.extend(
            run_embedding_check(
                run=inputs.run,
                live_models=inputs.live_models,
                blocked_provider_ids=blocked_provider_ids,
                readiness=inputs.readiness,
                resumable_results=inputs.resumable_results,
            )
        )
        return ordering.assemble(warnings)


def _incomplete_snapshot_warning() -> DriftWarning:
    return DriftWarning(
        kind=DriftKind.PROVIDER_REMOVED,
        severity=DriftSeverity.BLOCKING,
        headline=_INCOMPLETE_SNAPSHOT_HEADLINE,
        detail=_INCOMPLETE_SNAPSHOT_DETAIL,
    )
