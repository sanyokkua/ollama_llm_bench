"""Check 2 — test-model drift (spec §6.2)."""

from collections.abc import Mapping

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ModelNameStr,
    ModelRole,
    ProviderIdStr,
)
from ollama_llm_bench.backend.run_drift._internal.pending_results import count_by_target
from ollama_llm_bench.backend.run_drift.models import DriftKind, DriftSeverity, DriftWarning

__all__: list[str] = ["run_test_model_check"]


def run_test_model_check(
    *,
    run: BenchmarkRun,
    live_models: Mapping[ProviderIdStr, tuple[ModelNameStr, ...]],
    blocked_provider_ids: set[ProviderIdStr],
    resumable_results: tuple[BenchmarkResult, ...],
) -> list[DriftWarning]:
    """Run Check 2 over every ``TEST``-role model entry (spec §6.2).

    A model on a provider already ``BLOCKING``-warned by Check 1 is skipped —
    the provider warning already covers it, and its affected results are
    attributed to that provider warning, not duplicated here.

    Returns:
        The test-model-check warnings, advertisement-only (SPEC-048): presence
        in the live model listing, never loadability.
    """
    warnings: list[DriftWarning] = []
    for entry in run.models:
        if entry.role is not ModelRole.TEST:
            continue
        if entry.provider_id in blocked_provider_ids:
            continue
        live_names = live_models.get(entry.provider_id, ())
        if entry.model_name in live_names:
            continue
        affected = count_by_target(resumable_results, entry.provider_id, entry.model_name)
        warnings.append(
            DriftWarning(
                kind=DriftKind.MODEL_NO_LONGER_AVAILABLE,
                severity=DriftSeverity.BLOCKING,
                provider_id=entry.provider_id,
                model_name=entry.model_name,
                headline=f"Model '{entry.model_name}' is no longer available.",
                detail=f"{affected} pending task(s) would be affected." if affected else "",
                pending_results_affected=affected,
            )
        )
    return warnings
