"""Shared fixtures and factories for backend/performance_task_generator/tests/."""

import pytest

from ollama_llm_bench.backend.domain import PerformanceConfig, PositiveInt, RepeatCount
from ollama_llm_bench.backend.performance_task_generator import (
    PerformanceTaskGenerator,
    make_performance_task_generator,
)

VALID_SIZES: tuple[int, ...] = (64, 256, 1024, 4096, 16384)
SIZE_LABELS: dict[int, str] = {
    64: "tiny",
    256: "small",
    1024: "medium",
    4096: "large",
    16384: "xlarge",
}


@pytest.fixture
def generator() -> PerformanceTaskGenerator:
    """A fresh, stateless PerformanceTaskGenerator instance."""
    return make_performance_task_generator()


def make_performance_config(
    *,
    input_sizes: tuple[PositiveInt, ...] = (64,),
    output_sizes: tuple[PositiveInt, ...] = (64,),
    repeats: RepeatCount = 1,
) -> PerformanceConfig:
    """Build a minimal, otherwise-arbitrary valid `PerformanceConfig`."""
    return PerformanceConfig(input_sizes=input_sizes, output_sizes=output_sizes, repeats=repeats)
