"""Colocated tests for the §8 unknown-size validation error (STORY-034-AC-5)."""

import pytest

from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.performance_task_generator.tests.conftest import (
    make_performance_config,
)


def test_unknown_size_raises_and_returns_no_partial(
    generator: PerformanceTaskGenerator,
) -> None:
    """Proves: STORY-034-AC-5

    Given a PerformanceConfig whose axis carries a numeric size with no
    matching bucket, generate raises a validation error naming the offending
    value and returns no partial task list -- the call raises before
    returning anything.
    """
    # Arrange
    config = make_performance_config(input_sizes=(999,), output_sizes=(256,), repeats=1)

    # Act / Assert
    with pytest.raises(ContractViolationError, match="999"):
        generator.generate(config)
