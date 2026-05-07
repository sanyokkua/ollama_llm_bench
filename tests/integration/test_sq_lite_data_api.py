"""Integration tests for SqLiteDataApi — exercises real SQLite I/O."""

import dataclasses
import sqlite3

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
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
