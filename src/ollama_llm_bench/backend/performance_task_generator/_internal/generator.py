"""The concrete, stateless PerformanceTaskGenerator implementation (spec §6.1, §8, §9)."""

import icontract

from ollama_llm_bench.backend.domain import (
    BenchmarkTask,
    Difficulty,
    PerformanceConfig,
    RequiredTerms,
    TaskOrigin,
)
from ollama_llm_bench.backend.performance_task_generator._internal.prompt_builder import (
    _build_question,
)
from ollama_llm_bench.backend.performance_task_generator._internal.size_buckets import (
    _bucket_label,
)

__all__: list[str] = ["_PerformanceTaskGeneratorImpl"]


class _PerformanceTaskGeneratorImpl:
    """Stateless, synchronous, pure implementation of ``PerformanceTaskGenerator`` (spec §6)."""

    @icontract.require(
        lambda config: len(config.input_sizes) > 0,
        "config.input_sizes must be non-empty (spec §4, §8)",
    )
    @icontract.require(
        lambda config: len(config.output_sizes) > 0,
        "config.output_sizes must be non-empty (spec §4, §8)",
    )
    @icontract.require(
        lambda config: len(set(config.input_sizes)) == len(config.input_sizes),
        "config.input_sizes must contain no duplicate values (spec §4, §8)",
    )
    @icontract.require(
        lambda config: len(set(config.output_sizes)) == len(config.output_sizes),
        "config.output_sizes must contain no duplicate values (spec §4, §8)",
    )
    @icontract.ensure(
        lambda result, config: (
            len(result) == len(config.input_sizes) * len(config.output_sizes) * config.repeats
        ),
        "the returned tuple must have exactly len(input_sizes) x len(output_sizes) x "
        "repeats tasks (spec §3, §5)",
    )
    def generate(self, config: PerformanceConfig, /) -> tuple[BenchmarkTask, ...]:
        """Expand `config` into the deterministic synthetic task grid (spec §6.1).

        Args:
            config: The validated input/output size matrix and repeat count.

        Returns:
            One `BenchmarkTask` per `(input size x output size x repeat)`
            combination, ordered input ascending outermost, output ascending
            middle, repeat `1..repeats` innermost (spec §6.1 step 3).

        Raises:
            ContractViolationError: A numeric size in `config.input_sizes` or
                `config.output_sizes` matches no defined size bucket (spec §8) —
                a value the New Benchmark widget should never have produced.
        """
        tasks: list[BenchmarkTask] = []
        order = 0
        for input_size in sorted(config.input_sizes):
            input_label = _bucket_label(input_size)
            for output_size in sorted(config.output_sizes):
                output_label = _bucket_label(output_size)
                question = _build_question(input_size, output_size)
                for repeat_index in range(1, config.repeats + 1):
                    tasks.append(
                        _assemble_task(
                            input_label=input_label,
                            output_label=output_label,
                            question=question,
                            repeat_index=repeat_index,
                            task_order=order,
                        )
                    )
                    order += 1
        return tuple(tasks)


def _assemble_task(
    *,
    input_label: str,
    output_label: str,
    question: str,
    repeat_index: int,
    task_order: int,
) -> BenchmarkTask:
    """Construct one synthetic `BenchmarkTask` record (spec §3, §6.1 steps 5-6)."""
    task_id = f"perf_in-{input_label}_out-{output_label}_rep-{repeat_index:02d}"
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.SYNTHETIC,
        question=question,
        category="Synthetic Benchmark",
        sub_category=input_label,
        golden_answer=None,
        pass_criteria="",
        fail_criteria="",
        difficulty=Difficulty.MEDIUM,
        required_terms=RequiredTerms(),
        input_size_label=input_label,
        output_size_label=output_label,
        repeat_index=repeat_index,
        task_order=task_order,
    )
