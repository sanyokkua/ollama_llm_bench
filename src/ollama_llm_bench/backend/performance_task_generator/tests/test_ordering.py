"""Colocated tests for the fixed nesting order (STORY-034-AC-2)."""

from ollama_llm_bench.backend.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.performance_task_generator.tests.conftest import (
    SIZE_LABELS,
    make_performance_config,
)


def test_axes_sorted_and_repeats_contiguous(generator: PerformanceTaskGenerator) -> None:
    """Proves: STORY-034-AC-2

    Tasks are emitted with the input axis sorted ascending outermost, the
    output axis sorted ascending in the middle, and the repeat index
    1..repeats innermost, so all repeats of one (input, output) pair are
    contiguous.
    """
    # Arrange
    config = make_performance_config(input_sizes=(1024, 64), output_sizes=(256, 64), repeats=3)

    # Act
    result = generator.generate(config)

    # Assert -- first 3 tasks (one full inner repeat block) share the
    # smallest (input, output) pair and repeat_index runs 1..3 contiguously.
    first_block = result[:3]
    assert all(task.input_size_label == SIZE_LABELS[64] for task in first_block)
    assert all(task.output_size_label == SIZE_LABELS[64] for task in first_block)
    assert [task.repeat_index for task in first_block] == [1, 2, 3]

    # Assert -- the pair sequence itself follows input-ascending-outer,
    # output-ascending-middle across the whole grid.
    pair_sequence = [(task.input_size_label, task.output_size_label) for task in result[::3]]
    assert pair_sequence == [
        (SIZE_LABELS[64], SIZE_LABELS[64]),
        (SIZE_LABELS[64], SIZE_LABELS[256]),
        (SIZE_LABELS[1024], SIZE_LABELS[64]),
        (SIZE_LABELS[1024], SIZE_LABELS[256]),
    ]
