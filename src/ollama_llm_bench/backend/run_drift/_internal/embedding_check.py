"""Check 4 — embedding drift (spec §6.4)."""

from collections.abc import Mapping

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    ModelNameStr,
    ModelRole,
    ProviderIdStr,
)
from ollama_llm_bench.backend.run_drift._internal.pending_results import count_by_target
from ollama_llm_bench.backend.run_drift._internal.settings_flags import needs_cosine_phase
from ollama_llm_bench.backend.run_drift.models import DriftKind, DriftSeverity, DriftWarning

__all__: list[str] = ["run_embedding_check"]


def run_embedding_check(
    *,
    run: BenchmarkRun,
    live_models: Mapping[ProviderIdStr, tuple[ModelNameStr, ...]],
    blocked_provider_ids: set[ProviderIdStr],
    readiness: AppReadinessSnapshot | None,
    resumable_results: tuple[BenchmarkResult, ...],
) -> list[DriftWarning]:
    """Run Check 4 over the run's frozen ``EMBEDDING``-role pair, if any (spec §6.4).

    Skipped entirely when the frozen snapshot's ``eval.phase_cosine_enabled`` is
    false. Checks the FROZEN pair only — never the live embedding selection
    (DD-57): a changed live selection is not drift.

    Returns:
        Zero or one embedding-drift warning (``EMBEDDING_NOW_UNREACHABLE`` or
        ``EMBEDDING_MODEL_UNAVAILABLE``).
    """
    if not needs_cosine_phase(run.settings_snapshot):
        return []
    embedding_entry = _find_embedding_entry(run.models)
    if embedding_entry is None:
        return []
    if embedding_entry.provider_id in blocked_provider_ids:
        return [
            _unreachable_warning(
                embedding_entry, resumable_results, detail="see the provider warning above"
            )
        ]
    if not _provider_reachable(embedding_entry.provider_id, readiness):
        return [_unreachable_warning(embedding_entry, resumable_results, detail="")]
    live_names = live_models.get(embedding_entry.provider_id, ())
    if embedding_entry.model_name in live_names:
        return []
    return [_model_unavailable_warning(embedding_entry, resumable_results)]


def _find_embedding_entry(
    models: tuple[BenchmarkRunModelEntry, ...],
) -> BenchmarkRunModelEntry | None:
    for entry in models:
        if entry.role is ModelRole.EMBEDDING:
            return entry
    return None


def _provider_reachable(provider_id: ProviderIdStr, readiness: AppReadinessSnapshot | None) -> bool:
    if readiness is None:
        return False
    for health in readiness.per_provider:
        if health.provider_id == provider_id:
            return health.reachable
    return False


def _unreachable_warning(
    entry: BenchmarkRunModelEntry, resumable_results: tuple[BenchmarkResult, ...], *, detail: str
) -> DriftWarning:
    affected = count_by_target(resumable_results, entry.provider_id, entry.model_name)
    return DriftWarning(
        kind=DriftKind.EMBEDDING_NOW_UNREACHABLE,
        severity=DriftSeverity.BLOCKING,
        provider_id=entry.provider_id,
        model_name=entry.model_name,
        headline=f"Embedding model '{entry.model_name}' is no longer reachable.",
        detail=detail,
        pending_results_affected=affected,
    )


def _model_unavailable_warning(
    entry: BenchmarkRunModelEntry, resumable_results: tuple[BenchmarkResult, ...]
) -> DriftWarning:
    affected = count_by_target(resumable_results, entry.provider_id, entry.model_name)
    return DriftWarning(
        kind=DriftKind.EMBEDDING_MODEL_UNAVAILABLE,
        severity=DriftSeverity.BLOCKING,
        provider_id=entry.provider_id,
        model_name=entry.model_name,
        headline=f"Embedding model '{entry.model_name}' is no longer served by its provider.",
        detail="",
        pending_results_affected=affected,
    )
