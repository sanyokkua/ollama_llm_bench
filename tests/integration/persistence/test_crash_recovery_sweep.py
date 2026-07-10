"""Integration tests for the ``ResultsStore`` crash-recovery sweep.

Exercises ``recover_in_flight_results`` against a real ``tmp_path`` SQLite
database file, never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-011 acceptance criteria AC-3, AC-4.
"""

from pathlib import Path
import sqlite3

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
    RunId,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import ResultsStore, create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"

_MID_FLIGHT_STATUSES = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)
_UNCHANGED_STATUSES = (
    ResultStatus.PENDING,
    ResultStatus.COMPLETED,
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)


@pytest.fixture
def results_store(db_path: Path, clock: Clock) -> tuple[ResultsStore, sqlite3.Connection, RunId]:
    """A ``ResultsStore`` wired over a fresh ``tmp_path`` database, plus the write
    connection and a real parent run id with one parent task created via
    ``RunsStore``/``TasksStore``.
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    read_conn_factory = lambda: open_read_connection(db_path)  # noqa: E731  # local test helper
    runs_store = create_runs_store(write_conn, lock, read_conn_factory)
    run_id = runs_store.create_run(_make_run())
    tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
    tasks_store.create_tasks(run_id, (_make_task("task-1"),))
    store = create_results_store(write_conn, lock, read_conn_factory)
    return store, write_conn, run_id


def _make_run() -> BenchmarkRun:
    """Build a placeholder ``BenchmarkRun`` sufficient to create a parent run row."""
    return BenchmarkRun(
        run_id=-1,
        run_name="parent-run",
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name="llama3"
            ),
        ),
    )


def _make_task(task_id: str) -> BenchmarkTask:
    """Build a minimal valid parent ``BenchmarkTask``."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        question="What is 2+2?",
    )


def _make_result(*, run_id: RunId, status: ResultStatus) -> BenchmarkResult:
    """Build a minimal valid ``BenchmarkResult`` in the given status, carrying one
    term child row and a non-null ``sanitized_response`` so the sweep's
    child-row-clearing step is observable.
    """
    return BenchmarkResult(
        result_id=-1,
        run_id=run_id,
        task_id="task-1",
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


@pytest.mark.parametrize("status", list(ResultStatus))
def test_sweep_resets_only_the_four_mid_flight_statuses(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
    status: ResultStatus,
) -> None:
    """Proves: STORY-011-AC-3

    The crash-recovery sweep resets a result row to PENDING (clearing its
    child rows and in-flight columns) when it is in one of the four
    non-terminal in-flight statuses, and leaves every other status —
    PENDING and the six terminal statuses — untouched.
    """
    store, _write_conn, run_id = results_store
    store.create_results((_make_result(run_id=run_id, status=status),))
    original = store.list_results(run_id)[0]
    result_id = original.result_id

    # Act
    reset_count = store.recover_in_flight_results()
    swept = next(r for r in store.list_results(run_id) if r.result_id == result_id)

    if status in _MID_FLIGHT_STATUSES:
        assert reset_count == 1
        assert swept.status == ResultStatus.PENDING
        assert swept.sanitized_response is None
        assert swept.terms == ()
    else:
        assert status in _UNCHANGED_STATUSES
        assert reset_count == 0
        assert swept.status == status
        assert swept.sanitized_response == "in-flight response"
        assert len(swept.terms) == 1


def test_recover_in_flight_results_is_idempotent(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-011-AC-4

    Given a database containing result rows across every status, when
    recover_in_flight_results is called twice in succession, then the
    second call resets zero additional rows and the database state after
    the second call is identical to the state after the first.
    """
    store, write_conn, run_id = results_store
    store.create_results(
        tuple(_make_result(run_id=run_id, status=status) for status in ResultStatus)
    )

    # Act — first sweep resets exactly the mid-flight rows.
    first_reset_count = store.recover_in_flight_results()
    assert first_reset_count == len(_MID_FLIGHT_STATUSES)
    state_after_first = _snapshot_all_result_rows(write_conn)

    # Act — second sweep is a no-op.
    second_reset_count = store.recover_in_flight_results()
    state_after_second = _snapshot_all_result_rows(write_conn)

    # Assert — idempotent: zero additional rows reset, byte-identical state.
    assert second_reset_count == 0
    assert state_after_second == state_after_first


def _snapshot_all_result_rows(write_conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    """Re-``SELECT *`` every ``benchmark_results`` row, ordered deterministically."""
    rows = write_conn.execute("SELECT * FROM benchmark_results ORDER BY result_id ASC").fetchall()
    return [tuple(row) for row in rows]
