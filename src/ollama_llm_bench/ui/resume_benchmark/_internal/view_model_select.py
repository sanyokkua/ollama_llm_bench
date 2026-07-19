"""Pure ``BenchmarkRun[] -> RunRow[]`` derivation for the Resume run table (STORY-056).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``
§3.3 (run table columns), §4.1 (resumable classification), §4.3 (status badge),
``07_Common_Dialogs/rename_run_dialog.md`` §1 (default-name template, SPEC-077).

No Qt, no I/O -- ``log_file_exists``/``active_run_id`` are pre-fetched by the
controller and passed in so this module stays directly unit-testable.
"""

from collections.abc import Mapping
from datetime import datetime

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.ui.resume_benchmark.models import RunRow

__all__: list[str] = ["default_run_name", "effective_run_name", "select_run_rows"]

_STATUS_BADGE: dict[RunStatus, tuple[str, str]] = {
    RunStatus.COMPLETED: ("Done", "pass"),
    RunStatus.STOPPED: ("Stopped", "warning"),
    RunStatus.FAILED: ("Failed", "fail"),
    RunStatus.INCOMPLETE: ("Pending", "neutral"),
}

_MODE_LABELS: dict[RunMode, str] = {
    RunMode.SYNTHETIC: "Synthetic Benchmark",
    RunMode.TASKS: "Task Benchmark",
    RunMode.GRADED: "Graded Benchmark",
}

_RESUMABLE_RUN_STATUSES = (RunStatus.INCOMPLETE, RunStatus.STOPPED, RunStatus.FAILED)
_RESUMABLE_RESULT_STATUSES = (
    ResultStatus.PENDING,
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)


def select_run_rows(
    *,
    runs: tuple[BenchmarkRun, ...],
    results_by_run_id: Mapping[RunId, tuple[BenchmarkResult, ...]],
    active_run_id: RunId | None,
    log_file_exists_by_run_id: Mapping[RunId, bool],
) -> tuple[RunRow, ...]:
    """Derive display-ready RunRow tuples from raw run/result state.

    Args:
        runs: Every persisted run, in any order (the table model sorts).
        results_by_run_id: Each run's results, for the Tasks fraction and the
            ``is_resumable`` gate.
        active_run_id: The currently executing run's id, or None when idle.
        log_file_exists_by_run_id: Pre-checked log-file existence per run id.

    Returns:
        One RunRow per run, unsorted (sorting is the table model's job).
    """
    return tuple(
        _to_run_row(
            run,
            results=results_by_run_id.get(run.run_id, ()),
            active_run_id=active_run_id,
            log_file_exists=log_file_exists_by_run_id.get(run.run_id, False),
        )
        for run in runs
    )


def _to_run_row(
    run: BenchmarkRun,
    *,
    results: tuple[BenchmarkResult, ...],
    active_run_id: RunId | None,
    log_file_exists: bool,
) -> RunRow:
    completed = sum(1 for r in results if r.status is ResultStatus.COMPLETED)
    badge_label, badge_status = _STATUS_BADGE[run.status]
    is_executing = run.run_id == active_run_id
    has_resumable_result = any(r.status in _RESUMABLE_RESULT_STATUSES for r in results)
    is_resumable = (
        run.status in _RESUMABLE_RUN_STATUSES and has_resumable_result and not is_executing
    )
    return RunRow(
        run_id=run.run_id,
        effective_name=effective_run_name(run),
        mode_label=_MODE_LABELS[run.run_mode],
        started_at_display=_format_local(run.started_at) if run.started_at else "",
        started_at_sort_key=run.started_at or run.created_at,
        status_badge_label=badge_label,
        status_badge_status=badge_status,
        tasks_completed=completed,
        tasks_total=len(results),
        is_resumable=is_resumable,
        is_executing=is_executing,
        has_analysis=bool(run.run_analysis),
        log_file_exists=log_file_exists,
    )


def effective_run_name(run: BenchmarkRun) -> str:
    """The user-set name if present, otherwise the generated default name (SPEC-077)."""
    if run.run_name:
        return run.run_name
    return default_run_name(run_id=run.run_id, run_mode=run.run_mode, created_at=run.created_at)


def default_run_name(*, run_id: RunId, run_mode: RunMode, created_at: str) -> str:
    """Build the canonical generated default run-name (SPEC-077).

    Args:
        run_id: The run's numeric id.
        run_mode: The run's mode, for the display-label segment.
        created_at: The run's creation timestamp, ISO-8601 UTC.

    Returns:
        ``"Run N — <Mode display name> — YYYY-MM-DD HH:MM"``.
    """
    return f"Run {run_id} — {_MODE_LABELS[run_mode]} — {_format_local(created_at)}"


def _format_local(iso_timestamp: str) -> str:
    """Format an ISO-8601 UTC timestamp as local ``YYYY-MM-DD HH:MM``."""
    return datetime.fromisoformat(iso_timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
