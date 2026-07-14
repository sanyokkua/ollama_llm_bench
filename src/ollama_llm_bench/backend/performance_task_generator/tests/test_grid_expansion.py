"""Colocated tests for the cartesian grid expansion (STORY-034-AC-1)."""

import pytest

from ollama_llm_bench.backend.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.performance_task_generator.tests.conftest import (
    VALID_SIZES,
    make_performance_config,
)


@pytest.mark.parametrize(
    ("input_sizes", "output_sizes", "repeats"),
    [
        ((64,), (64,), 1),
        ((64, 256), (256, 1024), 3),
        (VALID_SIZES, VALID_SIZES, 50),
    ],
    ids=["1x1x1", "2x2x3", "5x5x50-maximum"],
)
def test_task_count_and_order_sequence(
    generator: PerformanceTaskGenerator,
    input_sizes: tuple[int, ...],
    output_sizes: tuple[int, ...],
    repeats: int,
) -> None:
    """Proves: STORY-034-AC-1

    Given a PerformanceConfig with i input sizes, o output sizes, and r
    repeats, the returned tuple has exactly i x o x r tasks, every task_id is
    unique within the tuple, and task_order runs 0..n-1 with no gaps and no
    duplicates.
    """
    # Arrange
    config = make_performance_config(
        input_sizes=input_sizes, output_sizes=output_sizes, repeats=repeats
    )
    expected_count = len(input_sizes) * len(output_sizes) * repeats

    # Act
    result = generator.generate(config)

    # Assert
    assert len(result) == expected_count
    assert len({task.task_id for task in result}) == expected_count
    assert [task.task_order for task in result] == list(range(expected_count))
