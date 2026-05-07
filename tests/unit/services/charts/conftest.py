"""Shared fixtures for chart aggregator unit tests."""

from __future__ import annotations

import pytest

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    RunMode,
)
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


@pytest.fixture
def make_result():
    """Factory fixture producing BenchmarkResult instances with sensible defaults."""

    def _make(**kwargs) -> BenchmarkResult:
        defaults: dict = {
            "model_name": "model_a",
            "task_id": "task_1",
            "task_category": "reasoning",
            "status": BenchmarkResultStatus.COMPLETED,
            "has_inference_error": False,
            "has_judge_error": False,
        }
        defaults.update(kwargs)
        return BenchmarkResult(**defaults)

    return _make


@pytest.fixture
def make_run():
    """Factory fixture producing BenchmarkRun instances with sensible defaults."""

    def _make(**kwargs) -> BenchmarkRun:
        defaults: dict = {
            "run_id": 1,
            "timestamp": "2024-01-01T00:00:00",
            "judge_model": "judge",
            "status": BenchmarkRunStatus.COMPLETED,
            "run_mode": RunMode.FULL_GRADING,
        }
        defaults.update(kwargs)
        return BenchmarkRun(**defaults)

    return _make


@pytest.fixture
def all_filters():
    """Fixture that returns a helper building a ChartFilters with all items included."""

    def _make(results: list[BenchmarkResult]) -> ChartFilters:
        models = list({r.model_name for r in results})
        categories = list({r.task_category for r in results})
        layers = list({r.resolution_layer for r in results if r.resolution_layer})
        return ChartFilters.all_included(models=models, categories=categories, layers=layers)

    return _make
