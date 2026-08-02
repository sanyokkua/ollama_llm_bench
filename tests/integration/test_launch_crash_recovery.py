"""Integration test for the launch-time crash-recovery sweep (STORY-080-AC-5)."""

import functools
from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkResultTerm,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    ResultStatus,
    ResultTermKind,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_IN_FLIGHT_STATUSES = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _shutdown(handle: AppHandle) -> None:
    handle.window.close()
    handle.shutdown(timeout_ms=2000)


def test_incomplete_run_left_for_resume_and_in_flight_rows_reset_to_pending(
    isolated_home: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-5 (EC-M-4)

    Given a database holding a run persisted `INCOMPLETE` whose result rows
    include one row in each of the four non-terminal in-flight statuses, each
    with child term rows, when the application launches, then the run's
    persisted status is still `INCOMPLETE`, every one of those four rows is
    `PENDING` with its child rows deleted, and the one terminal row is
    byte-for-byte unchanged.
    """
    # Arrange — seed the database directly, at the exact path build_app will open.
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    read_conn_factory = functools.partial(open_read_connection, db_path)
    runs_store = create_runs_store(write_conn, lock, read_conn_factory)
    run_id = runs_store.create_run(
        BenchmarkRun(
            run_id=-1,
            run_name="crashed-run",
            timestamp="2026-01-01T00:00:00+00:00",
            run_mode=RunMode.TASKS,
            status=RunStatus.INCOMPLETE,
            total_tasks=5,
            completed_tasks=1,
            total_elapsed_ms=0,
            schema_version=1,
            created_at="2026-01-01T00:00:00+00:00",
            models=(
                BenchmarkRunModelEntry(
                    role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name="llama3"
                ),
            ),
        )
    )
    tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
    task_ids = [f"task-{i}" for i in range(len(_IN_FLIGHT_STATUSES) + 1)]
    tasks_store.create_tasks(
        run_id,
        tuple(
            BenchmarkTask(task_id=t, task_origin=TaskOrigin.FILE, question="q") for t in task_ids
        ),
    )
    results_store = create_results_store(write_conn, lock, read_conn_factory)
    in_flight_rows = tuple(
        BenchmarkResult(
            result_id=-1,
            run_id=run_id,
            task_id=task_ids[i],
            provider_id=_TEST_PROVIDER_ID,
            provider_name="Local Ollama",
            model_name="llama3",
            status=status,
            sanitized_response="in-flight response",
            created_at="2026-01-01T00:00:00+00:00",
            terms=(
                BenchmarkResultTerm(term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="x"),
            ),
        )
        for i, status in enumerate(_IN_FLIGHT_STATUSES)
    )
    terminal_row = BenchmarkResult(
        result_id=-1,
        run_id=run_id,
        task_id=task_ids[-1],
        provider_id=_TEST_PROVIDER_ID,
        provider_name="Local Ollama",
        model_name="llama3",
        status=ResultStatus.COMPLETED,
        sanitized_response="a completed answer",
        created_at="2026-01-01T00:00:00+00:00",
    )
    results_store.create_results((*in_flight_rows, terminal_row))
    before_by_task = {r.task_id: r for r in results_store.list_results(run_id)}
    terminal_before = before_by_task[task_ids[-1]]
    write_conn.close()

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())
    try:
        after_write_conn, after_lock = open_write_connection(db_path)
        after_read_conn = functools.partial(open_read_connection, db_path)
        after_runs_store = create_runs_store(after_write_conn, after_lock, after_read_conn)
        after_results_store = create_results_store(after_write_conn, after_lock, after_read_conn)

        # Assert
        assert after_runs_store.get_run(run_id).status is RunStatus.INCOMPLETE
        after_by_task = {r.task_id: r for r in after_results_store.list_results(run_id)}
        for task_id in task_ids[: len(_IN_FLIGHT_STATUSES)]:
            swept = after_by_task[task_id]
            assert swept.status is ResultStatus.PENDING
            assert swept.terms == ()
            assert swept.sanitized_response is None
        terminal_after = after_by_task[task_ids[-1]]
        assert terminal_after == terminal_before
        after_write_conn.close()
    finally:
        _shutdown(handle)
