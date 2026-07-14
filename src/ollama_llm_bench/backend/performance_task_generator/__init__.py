"""Synthetic-task generator for SYNTHETIC.

Source of truth:
``docs/v3_specification/11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md``.

Expands a `PerformanceConfig` input-size x output-size x repeats grid into a
deterministic tuple of fully populated `BenchmarkTask` records, one per
combination, each carrying a deterministic padded prompt, a stable generated
`task_id`, synthetic markers, and no grading fields — so the rest of the
pipeline treats synthetic tasks identically to file tasks. The generator is
pure, stateless, and Qt-free; it persists nothing itself.
"""

from ollama_llm_bench.backend.performance_task_generator.api import (
    make_performance_task_generator,
)
from ollama_llm_bench.backend.performance_task_generator.protocols import (
    PerformanceTaskGenerator,
)

__all__: list[str] = ["PerformanceTaskGenerator", "make_performance_task_generator"]
