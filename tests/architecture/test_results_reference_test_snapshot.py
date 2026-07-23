"""SPEC-038 invariant: benchmark_results rows always match a role='test' snapshot row (STORY-074).

This is a DB-backed test placed under ``tests/architecture/`` — a deliberate deviation from
this directory's usual code-scanning tests, prescribed by the spec's edge-case mapping row for
EC-PERSIST-6 (tiers ``unit; architecture``; Invariant pattern). No foreign key can enforce the
invariant this module proves: the same ``(provider_id, model_name)`` pair may legitimately
appear under both a ``test`` and a ``judge`` role snapshot row for the same run (spec
``03_PERSISTENCE_SCHEMA.md`` §5.7), so a plain FK from ``benchmark_results`` to a single
``benchmark_run_models`` row cannot express "the test-role entry, specifically." The invariant
is therefore proven by a query, run here against both a production-write-path arrangement
(positive) and a hand-seeded rogue row (negative control).

``tests/architecture/`` has no conftest expectations to inherit for this module, so all
fixtures (``_FakeClock``, ``db_path``-shaped ``tmp_path`` usage) are kept module-local rather
than pulled from a shared conftest.
"""

from pathlib import Path

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store

_TEST_PROVIDER_ID_A = "11111111-1111-4111-8111-111111111111"
_TEST_PROVIDER_ID_B = "44444444-4444-4444-8444-444444444444"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_EMBEDDING_PROVIDER_ID = "33333333-3333-4333-8333-333333333333"

_ORPHAN_RESULTS_SQL = """
SELECT r.result_id
FROM benchmark_results AS r
LEFT JOIN benchmark_run_models AS m
    ON m.run_id = r.run_id
    AND m.role = 'test'
    AND m.provider_id = r.provider_id
    AND m.model_name = r.model_name
WHERE m.run_id IS NULL
"""


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


def _make_run() -> BenchmarkRun:
    """Build a ``BenchmarkRun`` snapshotting two TEST targets plus a JUDGE and an EMBEDDING entry."""
    return BenchmarkRun(
        run_id=-1,
        run_name="snapshot-invariant-run",
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        judge_provider_id=_JUDGE_PROVIDER_ID,
        judge_provider_name="OpenAI Judge",
        embedding_provider_name="OpenAI Embeddings",
        embedding_model_name="text-embedding-3",
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID_A, model_name="llama3"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID_B, model_name="mistral"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=_JUDGE_PROVIDER_ID, model_name="gpt-4o"
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.EMBEDDING,
                provider_id=_EMBEDDING_PROVIDER_ID,
                model_name="text-embedding-3",
            ),
        ),
    )


def _make_task() -> BenchmarkTask:
    """Build a minimal valid parent ``BenchmarkTask``."""
    return BenchmarkTask(
        task_id="task-1",
        task_origin=TaskOrigin.FILE,
        question="What is 2+2?",
    )


def _make_pending_result(*, run_id: RunId, provider_id: str, model_name: str) -> BenchmarkResult:
    """Build a minimal PENDING ``BenchmarkResult`` for one (task x snapshotted TEST target)."""
    return BenchmarkResult(
        result_id=-1,
        run_id=run_id,
        task_id="task-1",
        provider_id=provider_id,
        provider_name="Local Ollama",
        model_name=model_name,
        status=ResultStatus.PENDING,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_every_result_matches_a_test_role_snapshot_row(tmp_path: Path) -> None:
    """Proves: STORY-074-AC-5

    Rows written through the production write path (RunsStore.create_run
    snapshot + ResultsStore.create_results for snapshotted test targets
    only) always satisfy SPEC-038: every benchmark_results row's
    (run_id, provider_id, model_name) matches a role='test' snapshot row.
    """
    # Arrange
    db_path = tmp_path / "results_reference_test_snapshot_positive.db"
    clock = _FakeClock()
    write_conn, lock = open_write_connection(db_path)
    read_conn = open_read_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        read_conn_factory = lambda: open_read_connection(db_path)  # noqa: E731  # local test helper

        runs_store = create_runs_store(write_conn, lock, read_conn_factory)
        run_id = runs_store.create_run(_make_run())

        tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
        tasks_store.create_tasks(run_id, (_make_task(),))

        results_store = create_results_store(write_conn, lock, read_conn_factory)
        results_store.create_results(
            (
                _make_pending_result(
                    run_id=run_id, provider_id=_TEST_PROVIDER_ID_A, model_name="llama3"
                ),
                _make_pending_result(
                    run_id=run_id, provider_id=_TEST_PROVIDER_ID_B, model_name="mistral"
                ),
            )
        )

        # Act
        orphans = read_conn.execute(_ORPHAN_RESULTS_SQL).fetchall()

        # Assert
        assert orphans == []
    finally:
        read_conn.close()
        write_conn.rollback()
        write_conn.close()


def test_orphan_results_row_is_detected_by_the_invariant_query(tmp_path: Path) -> None:
    """Proves: STORY-074-AC-5

    Negative control: a hand-inserted results row naming a
    (run_id, provider_id, model_name) triple outside the run's test-role
    snapshot is flagged by the SPEC-038 invariant query — the check has teeth.
    """
    # Arrange
    db_path = tmp_path / "results_reference_test_snapshot_negative.db"
    clock = _FakeClock()
    write_conn, lock = open_write_connection(db_path)
    read_conn = open_read_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        read_conn_factory = lambda: open_read_connection(db_path)  # noqa: E731  # local test helper

        runs_store = create_runs_store(write_conn, lock, read_conn_factory)
        run_id = runs_store.create_run(_make_run())

        tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
        tasks_store.create_tasks(run_id, (_make_task(),))

        results_store = create_results_store(write_conn, lock, read_conn_factory)
        results_store.create_results(
            (
                _make_pending_result(
                    run_id=run_id, provider_id=_TEST_PROVIDER_ID_A, model_name="llama3"
                ),
            )
        )

        write_conn.execute(
            "INSERT INTO benchmark_results "
            "(run_id, task_id, provider_id, provider_name, model_name, status, created_at) "
            "VALUES (?, 'task-1', 'rogue-provider', 'Rogue Provider', 'rogue-model', "
            "'pending', '2026-01-01T00:00:00+00:00')",
            (run_id,),
        )
        write_conn.commit()
        rogue_result_id = write_conn.execute(
            "SELECT result_id FROM benchmark_results WHERE provider_id = 'rogue-provider'"
        ).fetchone()[0]

        # Act
        orphans = read_conn.execute(_ORPHAN_RESULTS_SQL).fetchall()

        # Assert — exactly the rogue row is flagged.
        assert [row[0] for row in orphans] == [rogue_result_id]
    finally:
        read_conn.close()
        write_conn.rollback()
        write_conn.close()
