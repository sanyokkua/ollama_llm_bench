"""Check 1 — provider drift (spec §6.1)."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ProviderConfig,
    ProviderHealth,
    ProviderIdStr,
)
from ollama_llm_bench.backend.run_drift._internal.pending_results import count_by_provider
from ollama_llm_bench.backend.run_drift.models import DriftKind, DriftSeverity, DriftWarning

__all__: list[str] = ["run_provider_check"]


@dataclass(slots=True)
class _ProviderCheckState:
    """The private, non-boundary-crossing mutable state of the provider check.

    Bundles the live/readiness lookups (read-only for the whole check) together
    with the accumulating warnings/blocked-providers result, so every helper
    below needs at most one context argument plus the identity of the provider
    it is currently evaluating.
    """

    live_by_id: Mapping[ProviderIdStr, ProviderConfig]
    health_by_id: Mapping[ProviderIdStr, ProviderHealth]
    readiness_present: bool
    process_environment: Mapping[str, str]
    resumable_results: tuple[BenchmarkResult, ...]
    warnings: list[DriftWarning] = field(default_factory=list)
    blocked_provider_ids: set[ProviderIdStr] = field(default_factory=set)


def run_provider_check(
    *,
    run: BenchmarkRun,
    live_providers: tuple[ProviderConfig, ...],
    readiness: AppReadinessSnapshot | None,
    process_environment: Mapping[str, str],
    resumable_results: tuple[BenchmarkResult, ...],
) -> tuple[list[DriftWarning], set[ProviderIdStr]]:
    """Run Check 1 over every snapshot provider (spec §6.1).

    For each ``BenchmarkRunProviderEntry`` in ``run.providers``, apply the live-state
    table: removed / disabled / unreachable (downgraded to ``WARNING`` when
    ``readiness`` is absent) / env-var missing (checked only when the frozen
    ``api_key_raw`` is non-empty). The env-var check tests only
    ``bool(process_environment.get(name))`` — the resolved value is never stored
    or returned.

    Returns:
        The provider-check warnings and the set of ``provider_id`` values that
        received a ``BLOCKING`` warning — Check 2/3/4 skip their per-model
        availability check for a provider already blocked here.
    """
    health_by_id = {} if readiness is None else {h.provider_id: h for h in readiness.per_provider}
    state = _ProviderCheckState(
        live_by_id={provider.provider_id: provider for provider in live_providers},
        health_by_id=health_by_id,
        readiness_present=readiness is not None,
        process_environment=process_environment,
        resumable_results=resumable_results,
    )

    for entry in run.providers:
        _check_one_provider(
            state, provider_id=entry.provider_id, frozen_api_key_raw=entry.api_key_raw
        )
    return state.warnings, state.blocked_provider_ids


def _check_one_provider(
    state: _ProviderCheckState, *, provider_id: ProviderIdStr, frozen_api_key_raw: str | None
) -> None:
    live = state.live_by_id.get(provider_id)
    if live is None:
        _emit(state, provider_id, kind=DriftKind.PROVIDER_REMOVED, reason="no longer configured")
        return
    if not live.enabled:
        _emit(state, provider_id, kind=DriftKind.PROVIDER_NOW_DISABLED, reason="now disabled")
        return
    if not _is_reachable(state, provider_id):
        severity = DriftSeverity.BLOCKING if state.readiness_present else DriftSeverity.WARNING
        reason = (
            "no longer reachable"
            if state.readiness_present
            else "reachability could not be checked"
        )
        _emit(
            state,
            provider_id,
            kind=DriftKind.PROVIDER_NOW_UNREACHABLE,
            reason=reason,
            severity=severity,
        )
        return
    if frozen_api_key_raw and not state.process_environment.get(frozen_api_key_raw):
        _emit(
            state,
            provider_id,
            kind=DriftKind.PROVIDER_ENV_VAR_MISSING,
            reason="its API-key environment variable is no longer set",
        )


def _is_reachable(state: _ProviderCheckState, provider_id: ProviderIdStr) -> bool:
    if not state.readiness_present:
        return False
    health = state.health_by_id.get(provider_id)
    return health is not None and health.reachable


def _emit(
    state: _ProviderCheckState,
    provider_id: ProviderIdStr,
    *,
    kind: DriftKind,
    reason: str,
    severity: DriftSeverity = DriftSeverity.BLOCKING,
) -> None:
    affected = count_by_provider(state.resumable_results, provider_id)
    warning = DriftWarning(
        kind=kind,
        severity=severity,
        provider_id=provider_id,
        headline=f"Provider '{provider_id}' {reason}.",
        detail=f"{affected} pending task(s) would be affected." if affected else "",
        pending_results_affected=affected,
    )
    state.warnings.append(warning)
    if severity is DriftSeverity.BLOCKING:
        state.blocked_provider_ids.add(provider_id)
