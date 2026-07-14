"""Shared test helpers and fixtures for ``backend/run_analysis/`` tests."""

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

__all__: list[str] = ["build_run_analysis_snapshot"]


def build_run_analysis_snapshot(  # noqa: PLR0913  # test helper exposes every overridable key
    *,
    judge_run_analysis_enabled: bool = True,
    benchmark_min_timeout_seconds: int = 300,
    benchmark_max_timeout_seconds: int = 900,
    benchmark_retry_count: int = 3,
    benchmark_consecutive_max_timeouts_to_exclude: int = 3,
    judge_min_seconds: int = 20,
    judge_max_seconds: int = 120,
    judge_escalation_steps: int = 2,
    judge_consecutive_threshold: int = 3,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a valid run-settings snapshot: the 8 adaptive-timeout keys the
    ``AdaptiveTimeoutService`` factory requires, plus the run-analysis feature flag.

    Args:
        judge_run_analysis_enabled: ``feature.judge_run_analysis_enabled`` override.
        benchmark_min_timeout_seconds: ``benchmark.min_timeout_seconds`` override.
        benchmark_max_timeout_seconds: ``benchmark.max_timeout_seconds`` override.
        benchmark_retry_count: ``benchmark.retry_count`` override.
        benchmark_consecutive_max_timeouts_to_exclude:
            ``benchmark.consecutive_max_timeouts_to_exclude`` override.
        judge_min_seconds: ``eval.judge_timeout_min_seconds`` override.
        judge_max_seconds: ``eval.judge_timeout_max_seconds`` override.
        judge_escalation_steps: ``eval.judge_timeout_escalation_steps`` override.
        judge_consecutive_threshold: ``eval.judge_timeout_consecutive_threshold`` override.

    Returns:
        A tuple of ``BenchmarkRunSettingEntry`` rows covering every key this
        module's service consults from a run snapshot.
    """
    values: dict[str, str] = {
        "feature.judge_run_analysis_enabled": str(judge_run_analysis_enabled).lower(),
        "benchmark.min_timeout_seconds": str(benchmark_min_timeout_seconds),
        "benchmark.max_timeout_seconds": str(benchmark_max_timeout_seconds),
        "benchmark.retry_count": str(benchmark_retry_count),
        "benchmark.consecutive_max_timeouts_to_exclude": str(
            benchmark_consecutive_max_timeouts_to_exclude
        ),
        "eval.judge_timeout_min_seconds": str(judge_min_seconds),
        "eval.judge_timeout_max_seconds": str(judge_max_seconds),
        "eval.judge_timeout_escalation_steps": str(judge_escalation_steps),
        "eval.judge_timeout_consecutive_threshold": str(judge_consecutive_threshold),
    }
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
        for key, value in values.items()
    )
