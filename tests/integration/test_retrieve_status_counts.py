"""Integration tests for SqLiteDataApi.retrieve_status_counts_for_run."""

import dataclasses
from pathlib import Path

import pytest

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
)
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def data_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.db")


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=0,
        timestamp="2026-01-01T00:00:00",
        judge_model="qwen3:8b",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )


def _make_result(run_id: int, task_id: str) -> BenchmarkResult:
    return BenchmarkResult(run_id=run_id, task_id=task_id, model_name="llama3.2:3b")


def test_retrieve_status_counts_for_run_returns_correct_counts(data_api: SqLiteDataApi) -> None:
    # Arrange
    run_id = data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_results([_make_result(run_id, f"t{i}") for i in range(4)])
    rows = data_api.retrieve_benchmark_results_for_run(run_id)
    data_api.update_benchmark_result(dataclasses.replace(rows[0], status=BenchmarkResultStatus.COMPLETED))
    data_api.update_benchmark_result(dataclasses.replace(rows[1], status=BenchmarkResultStatus.COMPLETED))
    data_api.update_benchmark_result(dataclasses.replace(rows[2], status=BenchmarkResultStatus.FAILED))

    # Act
    counts = data_api.retrieve_status_counts_for_run(run_id)

    # Assert
    assert counts[BenchmarkResultStatus.COMPLETED] == 2
    assert counts[BenchmarkResultStatus.FAILED] == 1
    assert counts[BenchmarkResultStatus.NOT_COMPLETED] == 1


def test_retrieve_status_counts_for_run_returns_empty_for_unknown_run(data_api: SqLiteDataApi) -> None:
    counts = data_api.retrieve_status_counts_for_run(99999)
    assert counts == {}


def test_retrieve_status_counts_for_run_only_includes_statuses_with_rows(data_api: SqLiteDataApi) -> None:
    run_id = data_api.create_benchmark_run(_make_run())
    data_api.create_benchmark_results([_make_result(run_id, "t1")])

    counts = data_api.retrieve_status_counts_for_run(run_id)

    assert BenchmarkResultStatus.NOT_COMPLETED in counts
    assert BenchmarkResultStatus.COMPLETED not in counts
    assert BenchmarkResultStatus.FAILED not in counts
