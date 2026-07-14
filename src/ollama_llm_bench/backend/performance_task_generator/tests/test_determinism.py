"""Colocated tests for determinism across calls and repeats (STORY-034-AC-4)."""

from hypothesis import given, strategies as st
import pytest

from ollama_llm_bench.backend.domain import PerformanceConfig
from ollama_llm_bench.backend.performance_task_generator import (
    PerformanceTaskGenerator,
    make_performance_task_generator,
)
from ollama_llm_bench.backend.performance_task_generator.tests.conftest import (
    VALID_SIZES,
    make_performance_config,
)


def test_generate_is_deterministic_and_prompts_identical_per_pair(
    generator: PerformanceTaskGenerator,
) -> None:
    """Proves: STORY-034-AC-4

    Given the same PerformanceConfig, two generate calls return identical
    task lists in identical order, and the repeats of one (input, output)
    pair carry byte-identical question text.
    """
    # Arrange
    config = make_performance_config(input_sizes=(256,), output_sizes=(1024,), repeats=3)

    # Act
    first_call = generator.generate(config)
    second_call = generator.generate(config)

    # Assert
    assert first_call == second_call
    questions = {task.question for task in first_call}
    assert len(questions) == 1


@pytest.mark.property
@given(
    input_sizes=st.lists(st.sampled_from(VALID_SIZES), min_size=1, max_size=5, unique=True),
    output_sizes=st.lists(st.sampled_from(VALID_SIZES), min_size=1, max_size=5, unique=True),
    repeats=st.integers(min_value=1, max_value=50),
)
def test_generate_is_deterministic_for_arbitrary_valid_configs(
    input_sizes: list[int], output_sizes: list[int], repeats: int
) -> None:
    """Proves: STORY-034-AC-4

    Property test: for any valid PerformanceConfig assembled from the fixed
    size buckets, two generate() calls with an identical config produce
    equal task tuples.
    """
    # Arrange
    config = PerformanceConfig(
        input_sizes=tuple(input_sizes), output_sizes=tuple(output_sizes), repeats=repeats
    )
    generator = make_performance_task_generator()

    # Act / Assert
    assert generator.generate(config) == generator.generate(config)
