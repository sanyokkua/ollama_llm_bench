"""Colocated tests for the synthetic field values of spec §3 (STORY-034-AC-3)."""

from ollama_llm_bench.backend.domain import RequiredTerms, TaskOrigin
from ollama_llm_bench.backend.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.performance_task_generator.tests.conftest import (
    make_performance_config,
)


def test_synthetic_markers_and_no_grading_fields(generator: PerformanceTaskGenerator) -> None:
    """Proves: STORY-034-AC-3

    For every generated synthetic task, task_origin == TaskOrigin.SYNTHETIC,
    category == "Synthetic Benchmark", golden_answer is None,
    pass_criteria/fail_criteria are empty, required_terms is empty, and
    input_size_label/output_size_label/repeat_index are all set.
    """
    # Arrange
    input_sizes = (64, 256)
    output_sizes = (64, 1024)
    repeats = 2
    expected_count = len(input_sizes) * len(output_sizes) * repeats
    config = make_performance_config(
        input_sizes=input_sizes, output_sizes=output_sizes, repeats=repeats
    )

    # Act
    result = generator.generate(config)

    # Assert
    assert len(result) == expected_count
    assert all(task.task_origin == TaskOrigin.SYNTHETIC for task in result)
    assert all(task.category == "Synthetic Benchmark" for task in result)
    assert all(task.golden_answer is None for task in result)
    assert all(task.pass_criteria == "" for task in result)
    assert all(task.fail_criteria == "" for task in result)
    assert all(task.required_terms == RequiredTerms() for task in result)
    assert all(task.input_size_label is not None for task in result)
    assert all(task.output_size_label is not None for task in result)
    assert all(task.repeat_index is not None for task in result)
