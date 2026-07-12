"""Check 3 — judge-model drift (spec §6.3)."""

from collections.abc import Mapping

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    ModelNameStr,
    ModelRole,
    ProviderIdStr,
)
from ollama_llm_bench.backend.run_drift._internal.pending_results import count_by_target
from ollama_llm_bench.backend.run_drift._internal.settings_flags import needs_judge
from ollama_llm_bench.backend.run_drift.models import DriftKind, DriftSeverity, DriftWarning

__all__: list[str] = ["run_judge_check"]


def run_judge_check(
    *,
    run: BenchmarkRun,
    live_models: Mapping[ProviderIdStr, tuple[ModelNameStr, ...]],
    blocked_provider_ids: set[ProviderIdStr],
    resumable_results: tuple[BenchmarkResult, ...],
) -> list[DriftWarning]:
    """Run Check 3 over the run's ``JUDGE``-role entry, if any (spec §6.3).

    Skipped entirely when neither ``eval.phase_judge_enabled`` nor
    ``feature.judge_run_analysis_enabled`` is true in the frozen snapshot — a
    judge model the run will never call cannot cause drift.

    Returns:
        Zero or one ``JUDGE_MODEL_UNAVAILABLE`` warning.
    """
    if not needs_judge(run.settings_snapshot):
        return []
    judge_entry = _find_judge_entry(run.models)
    if judge_entry is None:
        return []
    if judge_entry.provider_id in blocked_provider_ids:
        return [_warning(judge_entry, resumable_results, detail="see the provider warning above")]
    live_names = live_models.get(judge_entry.provider_id, ())
    if judge_entry.model_name in live_names:
        return []
    return [_warning(judge_entry, resumable_results, detail="")]


def _find_judge_entry(
    models: tuple[BenchmarkRunModelEntry, ...],
) -> BenchmarkRunModelEntry | None:
    for entry in models:
        if entry.role is ModelRole.JUDGE:
            return entry
    return None


def _warning(
    entry: BenchmarkRunModelEntry, resumable_results: tuple[BenchmarkResult, ...], *, detail: str
) -> DriftWarning:
    affected = count_by_target(resumable_results, entry.provider_id, entry.model_name)
    return DriftWarning(
        kind=DriftKind.JUDGE_MODEL_UNAVAILABLE,
        severity=DriftSeverity.BLOCKING,
        provider_id=entry.provider_id,
        model_name=entry.model_name,
        headline=f"Judge model '{entry.model_name}' is unavailable.",
        detail=detail,
        pending_results_affected=affected,
    )
