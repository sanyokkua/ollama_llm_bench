"""Integration tests for model-snapshot singleton enforcement via SQLite partial unique indexes.

Exercises the real ``RunsStore`` public surface and the underlying SQLite schema
constraints against a real ``tmp_path`` SQLite database file, never ``:memory:``,
per ``testing.md``'s integration-tier rule.

Source of truth: STORY-074 acceptance criteria AC-4.
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
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.runs import create_runs_store

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_EMBEDDING_PROVIDER_ID = "33333333-3333-4333-8333-333333333333"


def _make_run() -> BenchmarkRun:
    """Build a minimal ``BenchmarkRun`` for ``create_run`` calls.

    Returns a run with one TEST, one JUDGE, and one EMBEDDING entry.
    """
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
    providers = (
        BenchmarkRunProviderEntry(
            provider_id=_TEST_PROVIDER_ID,
            name="Local Ollama",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="http://localhost:11434",
        ),
    )
    settings_snapshot = (
        BenchmarkRunSettingEntry(setting_key="benchmark.retry_count", setting_value="3"),
    )
    return BenchmarkRun(
        run_id=-1,
        run_name="my-run",
        timestamp="2026-01-01T00:00:00+00:00",
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


@pytest.mark.parametrize(
    "role",
    [ModelRole.JUDGE, ModelRole.EMBEDDING],
    ids=["second-judge-row", "second-embedding-row"],
)
def test_second_judge_or_embedding_row_raises_unique_violation(
    role: ModelRole, db_path: Path, clock: Clock
) -> None:
    """Proves: STORY-074-AC-4

    The model-snapshot singletons are enforced by the database itself: a
    second judge (or embedding) row for the same run — with a different
    (provider_id, model_name), so the primary key cannot reject it — raises
    a UNIQUE violation via the partial indexes ux_run_models_one_judge /
    ux_run_models_one_embedding.
    """
    # Arrange — real schema on a tmp_path DB, one valid run persisted through the store
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        store = create_runs_store(write_conn, lock, lambda: open_read_connection(db_path))
        run_id = store.create_run(_make_run())

        # Control: a SECOND role='test' row passes — the enforcement is role-scoped,
        # i.e. it is the partial index, not a blanket run_id uniqueness.
        write_conn.execute(
            "INSERT INTO benchmark_run_models (run_id, role, provider_id, model_name)"
            " VALUES (?, 'test', ?, ?)",
            (run_id, "second-test-provider", "second-test-model"),
        )

        # Act / Assert — the singleton role's second row violates the partial unique index.
        with pytest.raises(
            sqlite3.IntegrityError, match=r"UNIQUE constraint failed: benchmark_run_models\.run_id"
        ):
            write_conn.execute(
                "INSERT INTO benchmark_run_models (run_id, role, provider_id, model_name)"
                " VALUES (?, ?, ?, ?)",
                (run_id, role.value, "another-provider", "another-model"),
            )
    finally:
        write_conn.rollback()
        write_conn.close()
