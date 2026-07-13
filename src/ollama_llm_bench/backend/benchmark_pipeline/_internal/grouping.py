"""Phase eligibility and (provider_id, model_name) grouping — pure functions, no I/O."""

from collections.abc import Iterable
from typing import Final

from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    ModelNameStr,
    ProviderIdStr,
    ResultStatus,
    RunMode,
)

_ELIGIBLE_STATUS_BY_PHASE: Final[dict[Phase, ResultStatus]] = {
    Phase.INFERENCE: ResultStatus.PENDING,
    Phase.KEYWORD_CHECK: ResultStatus.AWAITING_KEYWORD_CHECK,
    Phase.COSINE_CHECK: ResultStatus.AWAITING_COSINE_CHECK,
    Phase.JUDGE_CHECK: ResultStatus.AWAITING_JUDGE_CHECK,
}
"""The non-terminal `ResultStatus` each phase consumes rows from (08-B §5)."""

_GRADING_TOGGLE_BY_PHASE: Final[dict[Phase, str]] = {
    Phase.KEYWORD_CHECK: "keyword_enabled",
    Phase.COSINE_CHECK: "cosine_enabled",
    Phase.JUDGE_CHECK: "judge_enabled",
}
"""Maps a grading phase to the name of its resolved per-dimension toggle."""


def phase_applies(
    *,
    phase: Phase,
    run_mode: RunMode,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
) -> bool:
    """Return whether `phase` runs at all for this run (08-B §3.3).

    Args:
        phase: The pipeline phase being checked.
        run_mode: The run's fixed mode; only `GRADED` ever runs a grading phase.
        keyword_enabled: The run's resolved keyword-check toggle from its settings snapshot.
        cosine_enabled: The run's resolved cosine-check toggle from its settings snapshot.
        judge_enabled: The run's resolved judge-check toggle from its settings snapshot.

    Returns:
        `True` when `phase` executes for this run; `False` when it is skipped entirely.
    """
    if phase in (Phase.INITIALIZATION, Phase.INFERENCE):
        return True
    if run_mode is not RunMode.GRADED:
        return False
    toggles = {
        "keyword_enabled": keyword_enabled,
        "cosine_enabled": cosine_enabled,
        "judge_enabled": judge_enabled,
    }
    return toggles[_GRADING_TOGGLE_BY_PHASE[phase]]


def eligible_for_phase(
    results: Iterable[BenchmarkResult], *, phase: Phase
) -> tuple[BenchmarkResult, ...]:
    """Return the rows eligible to enter `phase`.

    A row is eligible iff its `status` is the non-terminal status `phase` produces
    from. A row already in a terminal status — `COMPLETED` or any `FAILED_*`/`ERRORED`
    from an earlier phase — is never eligible for a later phase (08-B §3.2).

    Args:
        results: The candidate result rows, in any order.
        phase: The phase about to run.

    Returns:
        The eligible rows, preserving their relative input order.
    """
    target_status = _ELIGIBLE_STATUS_BY_PHASE[phase]
    return tuple(result for result in results if result.status is target_status)


def group_by_provider_and_model(
    results: Iterable[BenchmarkResult],
) -> tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...]:
    """Group rows by `(provider_id, model_name)`, first-seen order preserved.

    Group order follows the first appearance of each `(provider_id, model_name)`
    pair in `results` — never alphabetized — so grouping matches the run's
    configured provider/model order and no provider switch occurs mid-group
    (08-B §4).

    Args:
        results: The rows to group, in the run's original task order.

    Returns:
        One `(provider_id, model_name, rows)` tuple per distinct pair, ordered by
        first appearance; `rows` preserves each row's relative input order.
    """
    order: list[tuple[ProviderIdStr, ModelNameStr]] = []
    buckets: dict[tuple[ProviderIdStr, ModelNameStr], list[BenchmarkResult]] = {}
    for result in results:
        key = (result.provider_id, result.model_name)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(result)
    return tuple(
        (provider_id, model_name, tuple(buckets[(provider_id, model_name)]))
        for provider_id, model_name in order
    )
