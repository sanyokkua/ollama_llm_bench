"""PerformanceTaskGenerator — generates BenchmarkTask list from a PerformanceConfig matrix."""

import logging

from ollama_llm_bench.backend.core.models import (
    BenchmarkTask,
    Difficulty,
    PerformanceConfig,
    PromptInputSize,
    PromptOutputSize,
    TaskType,
)
from ollama_llm_bench.backend.core.performance_prompts import build_performance_prompt

_logger = logging.getLogger(__name__)

_PERF_CATEGORY = "Performance"
_PERF_SUB_CATEGORY = "Throughput"


class PerformanceTaskGenerator:
    """Generates the cartesian product of (input_size x output_size x repeat) as BenchmarkTask instances."""

    def generate(self, config: PerformanceConfig) -> list[BenchmarkTask]:
        """Return all performance tasks implied by the matrix config.

        Args:
            config: Selected input/output size tiers and repetition count.

        Returns:
            Flat list of BenchmarkTask instances ordered by input_size,
            output_size, repeat_index.
        """
        tasks: list[BenchmarkTask] = []
        for input_size in config.input_sizes:
            for output_size in config.output_sizes:
                for repeat_index in range(config.repeat_count):
                    tasks.append(self._make_task(input_size, output_size, repeat_index))
        _logger.debug(
            "Generated %d performance tasks (%d input x %d output x %d repeats)",
            len(tasks),
            len(config.input_sizes),
            len(config.output_sizes),
            config.repeat_count,
        )
        return tasks

    def _make_task(
        self,
        input_size: PromptInputSize,
        output_size: PromptOutputSize,
        repeat_index: int,
    ) -> BenchmarkTask:
        task_id = f"perf_{input_size.value}_{output_size.value}_r{repeat_index}"
        return BenchmarkTask(
            task_id=task_id,
            category=_PERF_CATEGORY,
            sub_category=_PERF_SUB_CATEGORY,
            task_type=TaskType.FACTUAL_QA,
            question=build_performance_prompt(input_size, output_size),
            golden_answer="",
            pass_criteria="",
            fail_criteria="",
            difficulty=Difficulty.MEDIUM,
        )
