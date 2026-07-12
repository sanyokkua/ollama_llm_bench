"""Shared factory fixtures for backend/run_drift/tests/.

Each factory builds a minimal, otherwise-arbitrary satisfying instance of one of
the DTOs the detector consumes (``BenchmarkRun``, ``ProviderConfig``,
``AppReadinessSnapshot``, ``BenchmarkResult``), so every test overrides only the
one field it is exercising.
"""

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunProviderEntry,
    BenchmarkRunSettingEntry,
    ModelRole,
    ProviderConfig,
    ProviderHealth,
    ProviderIdStr,
    ProviderType,
    ReadinessState,
    ResultStatus,
    RunMode,
    RunStatus,
    Verdict,
)

DEFAULT_PROVIDER_ID: ProviderIdStr = "11111111-1111-4111-8111-111111111111"
JUDGE_PROVIDER_ID: ProviderIdStr = "22222222-2222-4222-8222-222222222222"
EMBEDDING_PROVIDER_ID: ProviderIdStr = "33333333-3333-4333-8333-333333333333"
DEFAULT_MODEL_NAME = "llama3"
DEFAULT_JUDGE_MODEL_NAME = "judge-model"
DEFAULT_EMBEDDING_MODEL_NAME = "nomic-embed-text"


def make_provider_config(
    *,
    provider_id: ProviderIdStr = DEFAULT_PROVIDER_ID,
    name: str = "provider",
    enabled: bool = True,
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary live ``ProviderConfig``."""
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=enabled,
    )


def make_provider_health(
    *, provider_id: ProviderIdStr = DEFAULT_PROVIDER_ID, reachable: bool = True
) -> ProviderHealth:
    """Build a minimal, otherwise-arbitrary ``ProviderHealth`` entry."""
    return ProviderHealth(
        provider_id=provider_id,
        reachable=reachable,
        discovery_supported=True,
        model_count=1,
        last_probe_ms=10,
        probed_at=0,
    )


def make_readiness_snapshot(
    *, per_provider: tuple[ProviderHealth, ...] = (), embedding_reachable: bool = True
) -> AppReadinessSnapshot:
    """Build a minimal, otherwise-arbitrary ``AppReadinessSnapshot``."""
    return AppReadinessSnapshot(
        overall=ReadinessState.READY,
        per_provider=per_provider,
        embedding_reachable=embedding_reachable,
    )


def make_run(
    *,
    providers: tuple[BenchmarkRunProviderEntry, ...] = (),
    models: tuple[BenchmarkRunModelEntry, ...] = (),
    settings_snapshot: tuple[BenchmarkRunSettingEntry, ...] = (),
    run_id: int = 1,
    status: RunStatus = RunStatus.STOPPED,
) -> BenchmarkRun:
    """Build a minimal, otherwise-arbitrary resumable ``BenchmarkRun``."""
    return BenchmarkRun(
        run_id=run_id,
        run_name="a run",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=RunMode.TASKS,
        status=status,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
        models=models,
        providers=providers,
        settings_snapshot=settings_snapshot,
    )


def make_provider_entry(
    *, provider_id: ProviderIdStr = DEFAULT_PROVIDER_ID, api_key_raw: str | None = None
) -> BenchmarkRunProviderEntry:
    """Build a minimal, otherwise-arbitrary frozen ``BenchmarkRunProviderEntry``."""
    return BenchmarkRunProviderEntry(
        provider_id=provider_id,
        name="provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key_raw=api_key_raw,
    )


def make_model_entry(
    *,
    role: ModelRole = ModelRole.TEST,
    provider_id: ProviderIdStr = DEFAULT_PROVIDER_ID,
    model_name: str = DEFAULT_MODEL_NAME,
) -> BenchmarkRunModelEntry:
    """Build a minimal, otherwise-arbitrary frozen ``BenchmarkRunModelEntry``."""
    return BenchmarkRunModelEntry(role=role, provider_id=provider_id, model_name=model_name)


def make_result(
    *,
    result_id: int = 1,
    provider_id: ProviderIdStr = DEFAULT_PROVIDER_ID,
    model_name: str = DEFAULT_MODEL_NAME,
    status: ResultStatus = ResultStatus.PENDING,
) -> BenchmarkResult:
    """Build a minimal, otherwise-arbitrary retryable ``BenchmarkResult``."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=1,
        task_id=f"task-{result_id}",
        provider_id=provider_id,
        provider_name="provider",
        model_name=model_name,
        status=status,
        created_at="2026-01-01T00:00:00Z",
    )


def make_setting_entry(*, setting_key: str, setting_value: str) -> BenchmarkRunSettingEntry:
    """Build one frozen per-run setting entry."""
    return BenchmarkRunSettingEntry(setting_key=setting_key, setting_value=setting_value)


def make_flags_snapshot(
    *,
    phase_judge_enabled: bool = False,
    judge_run_analysis_enabled: bool = False,
    phase_cosine_enabled: bool = False,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build the three gate-flag settings §7 reads, all defaulting to off."""
    return (
        make_setting_entry(
            setting_key="eval.phase_judge_enabled",
            setting_value="true" if phase_judge_enabled else "false",
        ),
        make_setting_entry(
            setting_key="feature.judge_run_analysis_enabled",
            setting_value="true" if judge_run_analysis_enabled else "false",
        ),
        make_setting_entry(
            setting_key="eval.phase_cosine_enabled",
            setting_value="true" if phase_cosine_enabled else "false",
        ),
    )


__all__ = [
    "DEFAULT_EMBEDDING_MODEL_NAME",
    "DEFAULT_JUDGE_MODEL_NAME",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_PROVIDER_ID",
    "EMBEDDING_PROVIDER_ID",
    "JUDGE_PROVIDER_ID",
    "Verdict",
    "make_flags_snapshot",
    "make_model_entry",
    "make_provider_config",
    "make_provider_entry",
    "make_provider_health",
    "make_readiness_snapshot",
    "make_result",
    "make_run",
    "make_setting_entry",
]
