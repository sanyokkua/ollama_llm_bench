"""Pure ``BenchmarkResult[] -> RetrySelectionViewModel`` derivation (STORY-057).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/retry_selection_dialog.md``
§4 (grouping), §5 (filter), §7 (pre-selection). No Qt, no I/O.
"""

from collections.abc import Sequence

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus, RunId
from ollama_llm_bench.ui.common_dialogs.models import (
    RetryFilterOption,
    RetryPickerRow,
    RetrySelectionViewModel,
)

__all__: list[str] = ["filter_group_for", "select_retry_selection_view_model", "visible_rows"]

_FAILED_RETRYABLE_STATUSES = (
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)
_CHIP_LABELS: dict[ResultStatus, str] = {
    ResultStatus.FAILED_INFERENCE: "Failed (provider)",
    ResultStatus.FAILED_PROVIDER: "Failed (provider)",
    ResultStatus.FAILED_TIMEOUT: "Failed (timeout)",
    ResultStatus.FAILED_JUDGE_TIMEOUT: "Failed (judge timeout)",
    ResultStatus.ERRORED: "Errored",
    ResultStatus.PENDING: "Pending",
    ResultStatus.RUNNING_INFERENCE: "In progress",
    ResultStatus.AWAITING_KEYWORD_CHECK: "In progress",
    ResultStatus.AWAITING_COSINE_CHECK: "In progress",
    ResultStatus.AWAITING_JUDGE_CHECK: "In progress",
}


def filter_group_for(status: ResultStatus) -> RetryFilterOption:
    """Classify a ``ResultStatus`` into its §4 Result Status Grouping bucket."""
    if status is ResultStatus.COMPLETED:
        return RetryFilterOption.ONLY_COMPLETED
    if status in _FAILED_RETRYABLE_STATUSES:
        return RetryFilterOption.ONLY_FAILED
    return RetryFilterOption.ONLY_INCOMPLETE


def select_retry_selection_view_model(
    *, run_id: RunId, results: tuple[BenchmarkResult, ...]
) -> RetrySelectionViewModel:
    """Derive the Retry Selection dialog's ViewModel, pre-selection applied once (§7)."""
    rows = tuple(_to_retry_row(result) for result in results)
    return RetrySelectionViewModel(run_id=run_id, rows=rows)


def visible_rows(
    rows: Sequence[RetryPickerRow], *, filter_option: RetryFilterOption
) -> tuple[RetryPickerRow, ...]:
    """Narrow ``rows`` to the ones the active filter shows (§5); ``ALL`` shows every row."""
    if filter_option is RetryFilterOption.ALL:
        return tuple(rows)
    return tuple(row for row in rows if row.filter_group is filter_option)


def _to_retry_row(result: BenchmarkResult) -> RetryPickerRow:
    group = filter_group_for(result.status)
    is_checked = group in (RetryFilterOption.ONLY_FAILED, RetryFilterOption.ONLY_INCOMPLETE)
    return RetryPickerRow(
        result_id=result.result_id,
        task_id=result.task_id,
        filter_group=group,
        status_chip_label=_chip_label(result),
        reason_text=_reason_text(result),
        is_checked=is_checked,
    )


def _chip_label(result: BenchmarkResult) -> str:
    if result.status is ResultStatus.COMPLETED:
        verdict = result.verdict.value.upper() if result.verdict is not None else "?"
        return f"Completed · {verdict}"
    return _CHIP_LABELS[result.status]


def _reason_text(result: BenchmarkResult) -> str:
    if result.error_message:
        return result.error_message
    if result.status is ResultStatus.COMPLETED and result.verdict is not None:
        return f"Verdict: {result.verdict.value.upper()}"
    return ""
