"""Integration tests for ``backend/persistence/tasks/``.

Exercises the real ``TasksStore`` public surface — ``create_tasks_store`` and the
``SqliteTasksStore`` it returns — against a real ``tmp_path`` SQLite database file,
never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-010 acceptance criteria AC-1, AC-2.
"""

from pathlib import Path
import sqlite3

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    RequiredTerms,
    RunId,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import TasksStore, create_tasks_store

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def tasks_store(db_path: Path, clock: Clock) -> tuple[TasksStore, sqlite3.Connection, RunId]:
    """A ``TasksStore`` wired over a fresh ``tmp_path`` database, plus the write
    connection and a real parent run id created via ``RunsStore``.
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    runs_store = create_runs_store(write_conn, lock, lambda: open_read_connection(db_path))
    run_id = runs_store.create_run(_make_run())
    store = create_tasks_store(write_conn, lock, lambda: open_read_connection(db_path))
    return store, write_conn, run_id


def _make_run() -> BenchmarkRun:
    """Build a placeholder ``BenchmarkRun`` sufficient to create a parent run row."""
    return BenchmarkRun(
        run_id=-1,
        run_name="parent-run",
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=2,
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


def test_create_tasks_writes_tasks_and_terms_atomically(
    tasks_store: tuple[TasksStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-010-AC-1

    Given a run and a tuple of BenchmarkTask values whose tasks carry exact,
    semantic, and forbidden terms, when create_tasks is called, then all
    benchmark_tasks rows and all their benchmark_task_terms child rows are
    written in one transaction, and a task declaring no required terms
    produces a task row with no term rows; and a second create_tasks call
    that forces a primary-key violation rolls back with zero surviving rows,
    proving the one-transaction guarantee.
    """
    store, write_conn, run_id = tasks_store
    task_with_terms = BenchmarkTask(
        task_id="task-1",
        task_origin=TaskOrigin.FILE,
        question="What is 2+2?",
        required_terms=RequiredTerms(
            exact=("four", "4"),
            semantic=("arithmetic",),
            forbidden=("wrong",),
        ),
        task_order=0,
    )
    task_without_terms = BenchmarkTask(
        task_id="task-2",
        task_origin=TaskOrigin.SYNTHETIC,
        question="What is the capital of France?",
        task_order=1,
    )

    # Act
    store.create_tasks(run_id, (task_with_terms, task_without_terms))

    # Assert — both benchmark_tasks rows exist.
    task_rows = write_conn.execute(
        "SELECT task_id FROM benchmark_tasks WHERE run_id = ? ORDER BY task_id", (run_id,)
    ).fetchall()
    assert [row[0] for row in task_rows] == ["task-1", "task-2"]

    # Assert — exactly the expected term rows exist for the task with terms.
    term_rows = write_conn.execute(
        "SELECT term_kind, term_order, term_text FROM benchmark_task_terms "
        "WHERE run_id = ? AND task_id = ? ORDER BY term_kind, term_order",
        (run_id, "task-1"),
    ).fetchall()
    assert term_rows == [
        ("exact", 0, "four"),
        ("exact", 1, "4"),
        ("forbidden", 0, "wrong"),
        ("semantic", 0, "arithmetic"),
    ]

    # Assert — zero term rows exist for the task without terms.
    no_term_rows = write_conn.execute(
        "SELECT COUNT(*) FROM benchmark_task_terms WHERE run_id = ? AND task_id = ?",
        (run_id, "task-2"),
    ).fetchone()[0]
    assert no_term_rows == 0

    # Act 2 — a duplicate task_id within one tuple forces a primary-key violation.
    tasks_before = write_conn.execute(
        "SELECT COUNT(*) FROM benchmark_tasks WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    duplicate_task = BenchmarkTask(
        task_id="task-3",
        task_origin=TaskOrigin.FILE,
        question="Duplicate?",
        task_order=2,
    )

    with pytest.raises(PersistenceError):
        store.create_tasks(run_id, (duplicate_task, duplicate_task))

    # Assert — the whole transaction rolls back, no partial row survives.
    tasks_after = write_conn.execute(
        "SELECT COUNT(*) FROM benchmark_tasks WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    assert tasks_after == tasks_before


def test_list_tasks_returns_tasks_in_order_with_terms(
    tasks_store: tuple[TasksStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-010-AC-2

    Given a run's persisted task snapshot, list_tasks returns the tasks in
    ascending task_order, each assembled with its exact/semantic/forbidden
    term child rows, and returns an empty tuple for a run that has no tasks.
    """
    store, _write_conn, run_id = tasks_store

    # Assert — a fresh run with no tasks returns an empty tuple.
    assert store.list_tasks(run_id) == ()

    # Arrange — insert two tasks out of task_order sequence.
    second_task = BenchmarkTask(
        task_id="task-second",
        task_origin=TaskOrigin.FILE,
        question="Second question?",
        required_terms=RequiredTerms(exact=("beta",), forbidden=("nope", "never")),
        task_order=1,
    )
    first_task = BenchmarkTask(
        task_id="task-first",
        task_origin=TaskOrigin.SYNTHETIC,
        question="First question?",
        required_terms=RequiredTerms(semantic=("alpha", "primary")),
        task_order=0,
    )
    store.create_tasks(run_id, (second_task, first_task))

    # Act
    listed = store.list_tasks(run_id)

    # Assert — ascending task_order, not insertion order.
    assert [task.task_id for task in listed] == ["task-first", "task-second"]

    # Assert — each task's required_terms is correctly assembled and ordered per kind.
    assert listed[0].required_terms == RequiredTerms(semantic=("alpha", "primary"))
    assert listed[1].required_terms == RequiredTerms(exact=("beta",), forbidden=("nope", "never"))
