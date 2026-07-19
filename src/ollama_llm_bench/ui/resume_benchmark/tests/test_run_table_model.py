"""Colocated unit tests for ui/resume_benchmark's run table (STORY-056)."""

from PySide6.QtTest import QAbstractItemModelTester
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultStatus,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import RunTableModel
from ollama_llm_bench.ui.resume_benchmark._internal.view_model_select import select_run_rows
from ollama_llm_bench.ui.resume_benchmark.models import RunRow


def _run(run_id: int, *, status: RunStatus, run_name: str | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=status,
        total_tasks=2,
        completed_tasks=1,
        total_elapsed_ms=1000,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
        started_at="2024-01-02T10:30:00+00:00",
    )


def _result(result_id: int, *, run_id: int, status: ResultStatus) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        created_at="2024-01-01T00:00:00+00:00",
    )


def test_status_badge_per_run_status() -> None:
    """Proves: STORY-056-AC-3

    Each RunStatus maps to its exact badge label/tone pair, table-driven over
    all four persisted statuses (also covers EC-PERSIST-2: INCOMPLETE renders
    Pending and is offered as resumable).
    """
    cases = [
        (RunStatus.COMPLETED, "Done", "pass"),
        (RunStatus.STOPPED, "Stopped", "warning"),
        (RunStatus.FAILED, "Failed", "fail"),
        (RunStatus.INCOMPLETE, "Pending", "neutral"),
    ]
    for status, expected_label, expected_tone in cases:
        run = _run(1, status=status)
        results = (_result(1, run_id=1, status=ResultStatus.PENDING),)
        rows = select_run_rows(
            runs=(run,),
            results_by_run_id={1: results},
            active_run_id=None,
            log_file_exists_by_run_id={},
        )
        assert rows[0].status_badge_label == expected_label
        assert rows[0].status_badge_status == expected_tone
        if status is RunStatus.INCOMPLETE:
            assert rows[0].is_resumable is True


def test_completed_run_is_not_resumable() -> None:
    """Proves: STORY-056-AC-3

    A COMPLETED run is never resumable, even when a result is not COMPLETED.
    """
    run = _run(1, status=RunStatus.COMPLETED)
    results = (_result(1, run_id=1, status=ResultStatus.FAILED_INFERENCE),)
    rows = select_run_rows(
        runs=(run,),
        results_by_run_id={1: results},
        active_run_id=None,
        log_file_exists_by_run_id={},
    )
    assert rows[0].is_resumable is False


def test_executing_run_is_never_resumable() -> None:
    """Proves: STORY-056-AC-4

    A run that is currently executing is never resumable regardless of its
    status/result mix, and its is_executing flag is set.
    """
    run = _run(1, status=RunStatus.INCOMPLETE)
    results = (_result(1, run_id=1, status=ResultStatus.PENDING),)
    rows = select_run_rows(
        runs=(run,),
        results_by_run_id={1: results},
        active_run_id=1,
        log_file_exists_by_run_id={},
    )
    assert rows[0].is_executing is True
    assert rows[0].is_resumable is False


def test_effective_name_falls_back_to_generated_default() -> None:
    """Proves: STORY-056-AC-1

    A run with no custom name derives its effective_name from the generated
    default-name template.
    """
    run = _run(3, status=RunStatus.COMPLETED, run_name=None)
    rows = select_run_rows(
        runs=(run,),
        results_by_run_id={},
        active_run_id=None,
        log_file_exists_by_run_id={},
    )
    assert rows[0].effective_name.startswith("Run 3")
    assert "Task Benchmark" in rows[0].effective_name


def test_custom_run_name_used_verbatim() -> None:
    """Proves: STORY-056-AC-1

    A run with a custom name uses it verbatim as its effective_name.
    """
    run = _run(3, status=RunStatus.COMPLETED, run_name="My Run")
    rows = select_run_rows(
        runs=(run,),
        results_by_run_id={},
        active_run_id=None,
        log_file_exists_by_run_id={},
    )
    assert rows[0].effective_name == "My Run"


def _row(run_id: int, name: str, mode: str, started: str) -> RunRow:
    return RunRow(
        run_id=run_id,
        effective_name=name,
        mode_label=mode,
        started_at_display=started,
        started_at_sort_key=started,
        status_badge_label="Done",
        status_badge_status="pass",
        tasks_completed=1,
        tasks_total=1,
        is_resumable=False,
        is_executing=False,
        has_analysis=False,
        log_file_exists=False,
    )


_EXPECTED_ROW_COUNT = 3


def test_default_sort_and_name_or_mode_search(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-1

    Rows default to started_at descending; search filters by name OR mode,
    case-insensitively.
    """
    rows = (
        _row(1, "Alpha", "Synthetic Benchmark", "2024-01-01 00:00"),
        _row(2, "Beta", "Task Benchmark", "2024-01-03 00:00"),
        _row(3, "Gamma", "Graded Benchmark", "2024-01-02 00:00"),
    )
    model = RunTableModel(rows=rows)
    _tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    assert [model.visible_row(i).run_id for i in range(model.rowCount())] == [2, 3, 1]

    model.set_search_term("task")
    assert [model.visible_row(i).run_id for i in range(model.rowCount())] == [2]

    model.set_search_term("GAMMA")
    assert [model.visible_row(i).run_id for i in range(model.rowCount())] == [3]

    model.set_search_term("")
    assert model.rowCount() == _EXPECTED_ROW_COUNT


def test_set_sort_reorders_by_chosen_column(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-1

    Explicitly setting the sort column/direction re-orders the visible rows.
    """
    rows = (
        _row(1, "Alpha", "Synthetic Benchmark", "2024-01-01 00:00"),
        _row(2, "Beta", "Task Benchmark", "2024-01-03 00:00"),
    )
    model = RunTableModel(rows=rows)
    model.set_sort(0, descending=False)  # COL_NAME ascending
    assert [model.visible_row(i).run_id for i in range(model.rowCount())] == [1, 2]


def test_find_view_row_for_run_id_returns_none_when_absent(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-2

    find_view_row_for_run_id returns None when the run id is not visible.
    """
    model = RunTableModel(rows=(_row(1, "Alpha", "Synthetic Benchmark", "2024-01-01 00:00"),))
    assert model.find_view_row_for_run_id(999) is None
    assert model.find_view_row_for_run_id(1) == 0
