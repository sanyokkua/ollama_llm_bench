"""Integration tests for ``backend/persistence/runs/``.

Exercises the real ``RunsStore`` public surface — ``create_runs_store`` and the
``SqliteRunsStore`` it returns — against a real ``tmp_path`` SQLite database file,
never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-009 acceptance criteria AC-1, AC-2, AC-3.

``ResultsStore``/``TasksStore`` do not exist yet (STORY-010/STORY-011), so tests
that need "already-committed" descendant rows insert them with raw SQL directly
against the fixture's write connection, exactly as the story instructs.
"""

from pathlib import Path
import sqlite3

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunProviderEntry,
    BenchmarkRunSettingEntry,
    ModelRole,
    ProviderType,
    RunMode,
    RunStatus,
    RunStatusPatch,
)
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.runs import RunsStore, create_runs_store

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_EMBEDDING_PROVIDER_ID = "33333333-3333-4333-8333-333333333333"

_EXPECTED_TOTAL_TASKS = 5
_TERMINAL_COMPLETED_TASKS = 1
_TERMINAL_TOTAL_ELAPSED_MS = 1500
_UPDATED_COMPLETED_TASKS = 3
_UPDATED_TOTAL_ELAPSED_MS = 9000


@pytest.fixture
def runs_store(db_path: Path, clock: Clock) -> tuple[RunsStore, sqlite3.Connection]:
    """A ``RunsStore`` wired over a fresh ``tmp_path`` database, plus the write connection.

    The write connection is returned alongside the store so tests can execute raw
    SQL against the same physical database the store writes through (simulating
    already-committed descendant rows from stores that do not exist yet).
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    store = create_runs_store(write_conn, lock, lambda: open_read_connection(db_path))
    return store, write_conn


def _make_run(
    *,
    run_name: str | None = "my-run",
    timestamp: str = "2026-01-01T00:00:00+00:00",
    models: tuple[BenchmarkRunModelEntry, ...] | None = None,
    providers: tuple[BenchmarkRunProviderEntry, ...] | None = None,
    settings_snapshot: tuple[BenchmarkRunSettingEntry, ...] | None = None,
) -> BenchmarkRun:
    """Build a placeholder ``BenchmarkRun`` for ``create_run`` calls.

    ``run_id`` is a caller-supplied placeholder ``create_run`` ignores (the real
    id comes from SQLite's ``AUTOINCREMENT``-free ``INTEGER PRIMARY KEY``).
    """
    if models is None:
        models = (
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name="llama3"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=_JUDGE_PROVIDER_ID, model_name="gpt-4o"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.EMBEDDING,
                provider_id=_EMBEDDING_PROVIDER_ID,
                model_name="text-embedding-3",
            ),
        )
    if providers is None:
        providers = (
            BenchmarkRunProviderEntry(
                provider_id=_TEST_PROVIDER_ID,
                name="Local Ollama",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                base_url="http://localhost:11434",
            ),
        )
    if settings_snapshot is None:
        settings_snapshot = (
            BenchmarkRunSettingEntry(setting_key="benchmark.retry_count", setting_value="3"),
        )
    return BenchmarkRun(
        run_id=-1,
        run_name=run_name,
        timestamp=timestamp,
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=5,
        completed_tasks=0,
        total_elapsed_ms=0,
        judge_provider_id=_JUDGE_PROVIDER_ID,
        judge_provider_name="OpenAI Judge",
        embedding_provider_name="OpenAI Embeddings",
        embedding_model_name="text-embedding-3",
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=models,
        providers=providers,
        settings_snapshot=settings_snapshot,
    )


def test_create_run_writes_header_and_snapshots_atomically(
    runs_store: tuple[RunsStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-009-AC-1

    Given a BenchmarkRun carrying its model, provider, and settings snapshot
    collections, when create_run is called, then the benchmark_runs header and
    all three snapshot child tables are written in one transaction and get_run
    returns the run fully assembled with its snapshot collections in stable
    (sorted) order; and given a run whose model snapshot violates the
    ux_run_models_one_judge partial unique index (two judge-role entries),
    create_run raises PersistenceError with zero rows surviving in either
    benchmark_runs or benchmark_run_models for that attempt (full rollback, no
    orphan header row).
    """
    store, write_conn = runs_store
    run = _make_run()

    # Act
    new_run_id = store.create_run(run)

    # Assert — round trip through get_run, using the store-assigned id consistently.
    assembled = store.get_run(new_run_id)
    assert assembled.run_id == new_run_id
    assert assembled.run_name == "my-run"
    assert assembled.timestamp == "2026-01-01T00:00:00+00:00"
    assert assembled.run_mode == RunMode.TASKS
    assert assembled.status == RunStatus.INCOMPLETE
    assert assembled.total_tasks == _EXPECTED_TOTAL_TASKS
    assert assembled.completed_tasks == 0
    assert assembled.judge_provider_id == _JUDGE_PROVIDER_ID
    assert assembled.judge_provider_name == "OpenAI Judge"
    assert assembled.embedding_provider_name == "OpenAI Embeddings"
    assert assembled.embedding_model_name == "text-embedding-3"
    assert assembled.schema_version == 1
    assert assembled.created_at == "2026-01-01T00:00:00+00:00"

    # Snapshot collections round-trip fully, sorted deterministically by the store.
    expected_models = tuple(
        sorted(run.models, key=lambda m: (m.role.value, m.provider_id, m.model_name))
    )
    assert assembled.models == expected_models
    expected_providers = tuple(sorted(run.providers, key=lambda p: p.provider_id))
    assert assembled.providers == expected_providers
    expected_settings = tuple(sorted(run.settings_snapshot, key=lambda s: s.setting_key))
    assert assembled.settings_snapshot == expected_settings

    # Act 2 — a run with two judge-role model entries violates the partial unique index.
    conflicting_run = _make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=_JUDGE_PROVIDER_ID, model_name="gpt-4o"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=_EMBEDDING_PROVIDER_ID, model_name="claude-3"
            ),
        )
    )

    # Assert — the whole transaction rolls back, no partial header or snapshot row survives.
    runs_before = write_conn.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
    models_before = write_conn.execute("SELECT COUNT(*) FROM benchmark_run_models").fetchone()[0]

    with pytest.raises(PersistenceError):
        store.create_run(conflicting_run)

    runs_after = write_conn.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
    models_after = write_conn.execute("SELECT COUNT(*) FROM benchmark_run_models").fetchone()[0]
    assert runs_after == runs_before
    assert models_after == models_before


def test_terminal_header_write_comes_last_after_all_result_rows(
    runs_store: tuple[RunsStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-009-AC-2

    Given a run persisted with result rows already committed, when the caller
    finalises the run by issuing update_run_status with a terminal status, then
    the terminal header write is the last write of that run's write sequence —
    update_run_status structurally writes only the benchmark_runs table (every
    SQL statement it executes targets benchmark_runs and no other table), so a
    surviving terminal header implies every one of the run's result rows was
    committed before it.
    """
    store, write_conn = runs_store
    run_id = store.create_run(_make_run())

    # Arrange — simulate already-committed result rows via raw SQL (ResultsStore
    # does not exist yet; STORY-011 owns it).
    write_conn.execute(
        "INSERT INTO benchmark_tasks (run_id, task_id, task_origin, question) "
        "VALUES (?, ?, 'file', 'What is 2+2?')",
        (run_id, "task-1"),
    )
    write_conn.execute(
        "INSERT INTO benchmark_results "
        "(run_id, task_id, provider_id, provider_name, model_name, status, created_at) "
        "VALUES (?, 'task-1', ?, 'Local Ollama', 'llama3', 'completed', '2026-01-01T00:00:01+00:00')",
        (run_id, _TEST_PROVIDER_ID),
    )
    write_conn.commit()
    result_row_before = write_conn.execute(
        "SELECT status FROM benchmark_results WHERE run_id = ? AND task_id = 'task-1'", (run_id,)
    ).fetchone()

    # Act — capture every SQL statement executed during the terminal update.
    executed_statements: list[str] = []
    write_conn.set_trace_callback(executed_statements.append)
    try:
        store.update_run_status(
            run_id,
            RunStatusPatch(
                status=RunStatus.COMPLETED,
                completed_tasks=1,
                total_elapsed_ms=1500,
                finished_at="2026-01-01T00:00:02+00:00",
            ),
        )
    finally:
        write_conn.set_trace_callback(None)

    # Assert — the header reflects the terminal status/patch fields.
    finalised = store.get_run(run_id)
    assert finalised.status == RunStatus.COMPLETED
    assert finalised.completed_tasks == _TERMINAL_COMPLETED_TASKS
    assert finalised.total_elapsed_ms == _TERMINAL_TOTAL_ELAPSED_MS
    assert finalised.finished_at == "2026-01-01T00:00:02+00:00"

    # Assert — the simulated result row is untouched.
    result_row_after = write_conn.execute(
        "SELECT status FROM benchmark_results WHERE run_id = ? AND task_id = 'task-1'", (run_id,)
    ).fetchone()
    assert result_row_after == result_row_before
    assert result_row_after[0] == "completed"

    # Assert — every statement executed by update_run_status names only benchmark_runs,
    # never benchmark_results/benchmark_tasks/any other table — the structural proof
    # that this store's write path never touches result rows itself.
    other_table_names = (
        "benchmark_results",
        "benchmark_tasks",
        "benchmark_run_models",
        "benchmark_run_providers",
        "benchmark_run_settings",
        "benchmark_task_terms",
        "benchmark_result_terms",
        "benchmark_result_attempts",
    )
    assert executed_statements, "update_run_status must execute at least one statement"
    assert any("benchmark_runs" in stmt for stmt in executed_statements)
    assert not any(
        other_table in stmt for stmt in executed_statements for other_table in other_table_names
    )


def test_list_newest_first_update_status_and_cascade_delete(
    runs_store: tuple[RunsStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-009-AC-3

    Given several persisted runs, list_runs returns their headers newest-first
    by timestamp; update_run_status changes only the header's
    status/counter/timestamp columns and leaves the snapshot tables and
    identity columns untouched; delete_run removes the run and cascades to all
    eight descendant tables, leaving no orphan child row.
    """
    store, write_conn = runs_store

    # Arrange — create three runs out of chronological order.
    middle_id = store.create_run(
        _make_run(run_name="middle", timestamp="2026-02-01T00:00:00+00:00")
    )
    oldest_id = store.create_run(
        _make_run(run_name="oldest", timestamp="2026-01-01T00:00:00+00:00")
    )
    newest_id = store.create_run(
        _make_run(run_name="newest", timestamp="2026-03-01T00:00:00+00:00")
    )

    # Act
    listed = store.list_runs()

    # Assert — newest-first ordering by timestamp, independent of insertion order.
    listed_ids_in_order = [
        run.run_id for run in listed if run.run_id in {middle_id, oldest_id, newest_id}
    ]
    assert listed_ids_in_order == [newest_id, middle_id, oldest_id]

    # Arrange — snapshot the full header + snapshot state of one run before update_run_status.
    before = store.get_run(middle_id)

    # Act
    store.update_run_status(
        middle_id,
        RunStatusPatch(
            status=RunStatus.FAILED,
            completed_tasks=_UPDATED_COMPLETED_TASKS,
            total_elapsed_ms=_UPDATED_TOTAL_ELAPSED_MS,
        ),
    )
    after = store.get_run(middle_id)

    # Assert — only status-ish columns changed.
    assert after.status == RunStatus.FAILED
    assert after.completed_tasks == _UPDATED_COMPLETED_TASKS
    assert after.total_elapsed_ms == _UPDATED_TOTAL_ELAPSED_MS
    assert (before.status, before.completed_tasks, before.total_elapsed_ms) != (
        after.status,
        after.completed_tasks,
        after.total_elapsed_ms,
    )

    # Assert — identity columns and snapshot tables are byte-identical before/after.
    assert after.run_id == before.run_id
    assert after.timestamp == before.timestamp
    assert after.run_mode == before.run_mode
    assert after.total_tasks == before.total_tasks
    assert after.schema_version == before.schema_version
    assert after.created_at == before.created_at
    assert after.run_name == before.run_name
    assert after.models == before.models
    assert after.providers == before.providers
    assert after.settings_snapshot == before.settings_snapshot

    # Arrange — populate simulated rows in all eight descendant tables for one run.
    doomed_run_id = store.create_run(
        _make_run(run_name="doomed", timestamp="2026-04-01T00:00:00+00:00")
    )
    write_conn.execute(
        "INSERT INTO benchmark_tasks (run_id, task_id, task_origin, question) "
        "VALUES (?, 'task-x', 'file', 'Question?')",
        (doomed_run_id,),
    )
    write_conn.execute(
        "INSERT INTO benchmark_task_terms (run_id, task_id, term_kind, term_order, term_text) "
        "VALUES (?, 'task-x', 'exact', 0, 'answer')",
        (doomed_run_id,),
    )
    write_conn.execute(
        "INSERT INTO benchmark_results "
        "(run_id, task_id, provider_id, provider_name, model_name, status, created_at) "
        "VALUES (?, 'task-x', ?, 'Local Ollama', 'llama3', 'completed', '2026-04-01T00:00:01+00:00')",
        (doomed_run_id, _TEST_PROVIDER_ID),
    )
    doomed_result_id = write_conn.execute(
        "SELECT result_id FROM benchmark_results WHERE run_id = ? AND task_id = 'task-x'",
        (doomed_run_id,),
    ).fetchone()[0]
    write_conn.execute(
        "INSERT INTO benchmark_result_terms (result_id, term_kind, term_order, term_text) "
        "VALUES (?, 'exact_missing', 0, 'missing-term')",
        (doomed_result_id,),
    )
    write_conn.execute(
        "INSERT INTO benchmark_result_attempts "
        "(result_id, attempt_index, timeout_ms, outcome) VALUES (?, 1, 30000, 'success')",
        (doomed_result_id,),
    )
    write_conn.commit()

    # Sanity: every descendant table has at least one row belonging to doomed_run_id
    # (or, for the two result-scoped tables, keyed off doomed_result_id) before delete.
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM benchmark_run_models WHERE run_id = ?", (doomed_run_id,)
        ).fetchone()[0]
        > 0
    )
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM benchmark_results WHERE run_id = ?", (doomed_run_id,)
        ).fetchone()[0]
        > 0
    )

    # Act
    store.delete_run(doomed_run_id)

    # Assert — zero orphan rows remain in every one of the eight descendant tables.
    for table_name in ("benchmark_run_models", "benchmark_run_providers", "benchmark_run_settings"):
        remaining = write_conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE run_id = ?",  # noqa: S608  # table_name from a fixed local tuple, not user input
            (doomed_run_id,),
        ).fetchone()[0]
        assert remaining == 0, f"{table_name} still has rows for deleted run {doomed_run_id}"
    for table_name in ("benchmark_tasks", "benchmark_task_terms", "benchmark_results"):
        remaining = write_conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE run_id = ?",  # noqa: S608  # table_name from a fixed local tuple, not user input
            (doomed_run_id,),
        ).fetchone()[0]
        assert remaining == 0, f"{table_name} still has rows for deleted run {doomed_run_id}"
    for table_name in ("benchmark_result_terms", "benchmark_result_attempts"):
        remaining = write_conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE result_id = ?",  # noqa: S608  # table_name from a fixed local tuple, not user input
            (doomed_result_id,),
        ).fetchone()[0]
        assert remaining == 0, f"{table_name} still has rows for deleted result {doomed_result_id}"
