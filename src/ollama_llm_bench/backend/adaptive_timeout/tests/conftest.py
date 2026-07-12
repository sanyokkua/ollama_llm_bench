"""Shared test helpers for backend/adaptive_timeout/tests/."""

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry


def build_snapshot(  # noqa: PLR0913  # test helper must expose all 8 adaptive-timeout keys independently
    *,
    min_timeout_seconds: int = 300,
    max_timeout_seconds: int = 900,
    retry_count: int = 3,
    consecutive_max_timeouts_to_exclude: int = 3,
    judge_min_seconds: int = 20,
    judge_max_seconds: int = 120,
    judge_escalation_steps: int = 2,
    judge_consecutive_threshold: int = 3,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a valid 8-key adaptive-timeout snapshot (defaults per spec §7).

    Args:
        min_timeout_seconds: ``benchmark.min_timeout_seconds`` override.
        max_timeout_seconds: ``benchmark.max_timeout_seconds`` override.
        retry_count: ``benchmark.retry_count`` override (INFERENCE escalation steps).
        consecutive_max_timeouts_to_exclude: ``benchmark.consecutive_max_timeouts_to_exclude``
            override.
        judge_min_seconds: ``eval.judge_timeout_min_seconds`` override.
        judge_max_seconds: ``eval.judge_timeout_max_seconds`` override.
        judge_escalation_steps: ``eval.judge_timeout_escalation_steps`` override.
        judge_consecutive_threshold: ``eval.judge_timeout_consecutive_threshold`` override.

    Returns:
        A tuple of 8 ``BenchmarkRunSettingEntry`` rows, one per adaptive-timeout key.
    """
    values: dict[str, int] = {
        "benchmark.min_timeout_seconds": min_timeout_seconds,
        "benchmark.max_timeout_seconds": max_timeout_seconds,
        "benchmark.retry_count": retry_count,
        "benchmark.consecutive_max_timeouts_to_exclude": consecutive_max_timeouts_to_exclude,
        "eval.judge_timeout_min_seconds": judge_min_seconds,
        "eval.judge_timeout_max_seconds": judge_max_seconds,
        "eval.judge_timeout_escalation_steps": judge_escalation_steps,
        "eval.judge_timeout_consecutive_threshold": judge_consecutive_threshold,
    }
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=str(value))
        for key, value in values.items()
    )
