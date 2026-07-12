"""Runtime DTOs and enums owned by the Run Drift Detector (spec §3).

``DriftWarning``, ``DriftKind``, and ``DriftSeverity`` are produced fresh on every
resume attempt and are never persisted — they are explicitly NOT members of the
persisted-enum catalog in ``10_Domain_and_Data/02_DTOS_AND_ENUMS.md``.
"""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ModelNameStr,
    NonEmptyStr,
    NonNegativeInt,
    ProviderConfig,
    ProviderIdStr,
)

__all__: list[str] = [
    "DriftKind",
    "DriftSeverity",
    "DriftWarning",
    "RunDriftDetectionInputs",
]


class DriftSeverity(StrEnum):
    """Severity of one drift finding (spec §3)."""

    BLOCKING = "blocking"
    """Resume cannot succeed for the affected target without a fix."""

    WARNING = "warning"
    """An availability check could not be completed; resume may degrade."""


class DriftKind(StrEnum):
    """The kind of availability drift a single warning reports (spec §3)."""

    PROVIDER_NOW_DISABLED = "provider_now_disabled"
    PROVIDER_NOW_UNREACHABLE = "provider_now_unreachable"
    PROVIDER_REMOVED = "provider_removed"
    PROVIDER_ENV_VAR_MISSING = "provider_env_var_missing"
    MODEL_NO_LONGER_AVAILABLE = "model_no_longer_available"
    JUDGE_MODEL_UNAVAILABLE = "judge_model_unavailable"
    EMBEDDING_MODEL_UNAVAILABLE = "embedding_model_unavailable"
    EMBEDDING_NOW_UNREACHABLE = "embedding_now_unreachable"


class DriftWarning(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One availability-drift finding for the Resume Summary dialog (spec §3)."""

    kind: DriftKind
    severity: DriftSeverity
    provider_id: ProviderIdStr | None = None
    model_name: ModelNameStr | None = None
    headline: NonEmptyStr
    detail: str = ""
    pending_results_affected: NonNegativeInt = 0


class RunDriftDetectionInputs(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The already-gathered inputs the detector compares (spec §2).

    ``resumable_results`` is the run's already-gathered still-retryable
    ``BenchmarkResult`` rows — exactly what
    ``ResultsStore.list_resumable_results(run_id)`` returns. The detector never
    reads persistence itself (`backend/run_drift/` imports only
    `backend/domain`); the caller gathers this tuple once and passes it in.
    """

    run: BenchmarkRun
    live_providers: tuple[ProviderConfig, ...]
    live_models: dict[ProviderIdStr, tuple[ModelNameStr, ...]]
    process_environment: dict[str, str]
    readiness: AppReadinessSnapshot | None
    resumable_results: tuple[BenchmarkResult, ...]
