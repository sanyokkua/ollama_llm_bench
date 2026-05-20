"""Integration tests for SqLiteDataApi — exercises real SQLite I/O."""

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    PromptVariant,
)
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=0,
        timestamp="2026-01-01T00:00:00",
        judge_model="qwen3:8b",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )


def _make_result(run_id: int) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        task_id="t1",
        model_name="llama3.2:3b",
    )


def _make_variant(run_id: int, variant_id: str = "var_a") -> PromptVariant:
    return PromptVariant(
        variant_id=variant_id,
        run_id=run_id,
        variant_label="Variant A",
        user_prompt_template="Answer: {question}",
        created_at="2026-01-01T00:00:00",
    )


def test_create_and_retrieve_run(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())

    retrieved = data_api.retrieve_benchmark_run(run_id)

    assert retrieved.run_id == run_id
    assert retrieved.judge_model == "qwen3:8b"
    assert retrieved.status == BenchmarkRunStatus.NOT_COMPLETED


def test_update_run_status(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    run = data_api.retrieve_benchmark_run(run_id)

    updated = dataclasses.replace(run, status=BenchmarkRunStatus.FAILED)
    data_api.update_benchmark_run(updated)

    retrieved = data_api.retrieve_benchmark_run(run_id)
    assert retrieved.status == BenchmarkRunStatus.FAILED


def test_retrieve_all_runs_returns_all(data_api: SqLiteDataApi) -> None:
    data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_run(_make_run())

    all_runs = data_api.retrieve_benchmark_runs()

    assert len(all_runs) == 3


def test_create_and_retrieve_result(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    result_id = data_api.create_benchmark_result(_make_result(run_id))

    retrieved = data_api.retrieve_benchmark_result(result_id)

    assert retrieved.result_id == result_id
    assert retrieved.task_id == "t1"
    assert retrieved.model_name == "llama3.2:3b"


def test_retrieve_results_for_run(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_result(_make_result(run_id))
    data_api.create_benchmark_result(dataclasses.replace(_make_result(run_id), task_id="t2"))

    results = data_api.retrieve_benchmark_results_for_run(run_id)

    assert len(results) == 2


def test_set_and_get_app_setting(data_api: SqLiteDataApi) -> None:
    data_api.set_app_setting(key="ui.theme", value="light")
    setting = data_api.get_app_setting("ui.theme")

    assert setting is not None
    assert setting.value == "light"

    data_api.set_app_setting(key="ui.theme", value="dark")
    updated = data_api.get_app_setting("ui.theme")

    assert updated is not None
    assert updated.value == "dark"


def test_get_missing_setting_returns_none(data_api: SqLiteDataApi) -> None:
    result = data_api.get_app_setting("no.such.key")

    assert result is None


def test_create_and_retrieve_prompt_variants(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    data_api.create_prompt_variant(_make_variant(run_id, "var_a"))
    data_api.create_prompt_variant(_make_variant(run_id, "var_b"))

    variants = data_api.retrieve_prompt_variants_for_run(run_id)

    assert len(variants) == 2


def test_delete_run(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    assert len(data_api.retrieve_benchmark_runs()) == 1

    data_api.delete_benchmark_run(run_id)

    assert len(data_api.retrieve_benchmark_runs()) == 0


def test_schema_version_table_created_on_init(data_api: SqLiteDataApi) -> None:
    # Arrange — data_api fixture already initialized a fresh DB

    # Act
    conn = sqlite3.connect(data_api._db_path)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    conn.close()

    # Assert
    assert row is not None
    assert row[0] == 2


def test_benchmark_results_table_has_v2_columns(data_api: SqLiteDataApi) -> None:
    # Arrange — data_api fixture already initialized a fresh DB

    # Act
    conn = sqlite3.connect(data_api._db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(benchmark_results)").fetchall()}
    conn.close()

    # Assert — V2-specific columns that do not exist in a V1 schema
    assert "prompt_hash" in cols
    assert "has_thinking_block" in cols
    assert "cosine_similarity" in cols
    assert "resolution_layer" in cols
    assert "ttft_ms" in cols
    assert "raw_response" in cols
    assert "sanitized_response" in cols


def test_update_run_name_persists_and_retrieves(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())

    data_api.update_run_name(run_id=run_id, run_name="My Renamed Run")

    retrieved = data_api.retrieve_benchmark_run(run_id)
    assert retrieved.run_name == "My Renamed Run"


def test_run_name_is_none_by_default(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())

    retrieved = data_api.retrieve_benchmark_run(run_id)

    assert retrieved.run_name is None


def test_update_run_name_raises_on_duplicate(data_api: SqLiteDataApi) -> None:
    run_id_a = data_api.create_benchmark_run(_make_run())
    run_id_b = data_api.create_benchmark_run(_make_run())
    data_api.update_run_name(run_id=run_id_a, run_name="Same Name")

    with pytest.raises(sqlite3.IntegrityError):
        data_api.update_run_name(run_id=run_id_b, run_name="Same Name")


def test_multiple_null_run_names_allowed(data_api: SqLiteDataApi) -> None:
    data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_run(_make_run())

    all_runs = data_api.retrieve_benchmark_runs()

    assert all(r.run_name is None for r in all_runs)


def test_migration_adds_run_name_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE benchmark_runs (run_id INTEGER PRIMARY KEY, timestamp TEXT, status TEXT)")
    conn.commit()
    conn.close()

    SqLiteDataApi(db_path)

    conn2 = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn2.execute("PRAGMA table_info(benchmark_runs)").fetchall()}
    conn2.close()

    assert "run_name" in cols


# ---------------------------------------------------------------------------
# reset_results tests
# ---------------------------------------------------------------------------


def test_reset_results_clears_inferred_fields_and_preserves_identity(data_api: SqLiteDataApi) -> None:
    # Arrange — create a completed result with inferred fields populated
    run_id = data_api.create_benchmark_run(_make_run())
    base = _make_result(run_id)
    completed_result = dataclasses.replace(
        base,
        status=BenchmarkResultStatus.COMPLETED,
        completed_at="2026-01-02T00:00:00",
        raw_response="hello",
        sanitized_response="hello",
        response_char_length=5,
        has_thinking_block=True,
        total_time_ms=100,
        ttft_ms=10,
        prompt_tokens=5,
        completion_tokens=3,
        tokens_per_second=30.0,
        rule_check_result="pass",
        rule_check_resolved=True,
        keyword_check_resolved=True,
        cosine_similarity=0.9,
        cosine_resolved=True,
        judge_result="pass",
        judge_score=1.0,
        final_verdict="pass",
        resolution_layer="llm_judge",
        has_inference_error=False,
        has_judge_error=False,
    )
    result_id = data_api.create_benchmark_result(completed_result)

    # Act
    data_api.reset_results([result_id])

    # Assert — inferred fields are cleared; identity fields preserved
    retrieved = data_api.retrieve_benchmark_result(result_id)
    assert retrieved.status == BenchmarkResultStatus.NOT_COMPLETED
    assert retrieved.completed_at is None
    assert retrieved.raw_response is None
    assert retrieved.sanitized_response is None
    assert retrieved.response_char_length is None
    assert retrieved.has_thinking_block is False
    assert retrieved.total_time_ms is None
    assert retrieved.final_verdict is None
    assert retrieved.resolution_layer is None
    assert retrieved.has_inference_error is False
    # Identity fields are preserved
    assert retrieved.result_id == result_id
    assert retrieved.run_id == run_id
    assert retrieved.task_id == "t1"
    assert retrieved.model_name == "llama3.2:3b"


def test_reset_results_with_empty_list_is_noop(data_api: SqLiteDataApi) -> None:
    # Arrange
    run_id = data_api.create_benchmark_run(_make_run())
    result_id = data_api.create_benchmark_result(_make_result(run_id))

    # Act — calling with empty list should not raise and should not change anything
    data_api.reset_results([])

    retrieved = data_api.retrieve_benchmark_result(result_id)
    assert retrieved.status == BenchmarkResultStatus.NOT_COMPLETED


# ---------------------------------------------------------------------------
# Migration: fix COMPLETED runs with non-terminal results
# ---------------------------------------------------------------------------


def test_migration_corrects_completed_run_with_non_terminal_results(tmp_path: Path) -> None:
    # Arrange — insert a COMPLETED run with a WAITING_FOR_JUDGE result via raw SQL
    db_path = tmp_path / "migrate_test.db"
    run_id = SqLiteDataApi(db_path).create_benchmark_run(_make_run())
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE benchmark_runs SET status = 'COMPLETED' WHERE run_id = ?", (run_id,))
    conn.execute(
        "INSERT INTO benchmark_results (run_id, model_name, task_id, status) "
        "VALUES (?, 'model_a', 'task_a', 'WAITING_FOR_JUDGE')",
        (run_id,),
    )
    conn.commit()
    conn.close()

    # Act — re-init triggers migration
    api = SqLiteDataApi(db_path)

    # Assert — run should now be STOPPED
    run = api.retrieve_benchmark_run(run_id)
    assert run.status == BenchmarkRunStatus.STOPPED


def test_migration_is_idempotent(tmp_path: Path) -> None:
    # Arrange — create a DB then corrupt it
    db_path = tmp_path / "migrate_idem.db"
    api1 = SqLiteDataApi(db_path)
    run_id = api1.create_benchmark_run(_make_run())
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE benchmark_runs SET status = 'COMPLETED' WHERE run_id = ?", (run_id,))
    conn.execute(
        "INSERT INTO benchmark_results (run_id, model_name, task_id, status) "
        "VALUES (?, 'model_b', 'task_b', 'WAITING_FOR_JUDGE')",
        (run_id,),
    )
    conn.commit()
    conn.close()

    # Act — re-init twice
    api2 = SqLiteDataApi(db_path)
    api3 = SqLiteDataApi(db_path)

    # Assert — no exception, still STOPPED after two migrations
    run = api3.retrieve_benchmark_run(run_id)
    assert run.status == BenchmarkRunStatus.STOPPED
    # Suppress unused-variable warning for api2
    _ = api2
