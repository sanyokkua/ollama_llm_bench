"""Public factory for the Performance Task Generator (spec §6)."""

import icontract

from ollama_llm_bench.backend.performance_task_generator._internal.generator import (
    _PerformanceTaskGeneratorImpl,
)
from ollama_llm_bench.backend.performance_task_generator._internal.size_buckets import (
    SIZE_BUCKETS,
)
from ollama_llm_bench.backend.performance_task_generator.protocols import (
    PerformanceTaskGenerator,
)

__all__: list[str] = ["SIZE_BUCKETS", "make_performance_task_generator"]


@icontract.ensure(
    lambda result: result is not None,
    "factory must return a usable generator instance",
)
def make_performance_task_generator() -> PerformanceTaskGenerator:
    """Construct the stateless Performance Task Generator (spec §6).

    Returns:
        A pure, synchronous PerformanceTaskGenerator with no constructor
        collaborators — every expansion operates only on the PerformanceConfig
        passed to generate().
    """
    return _PerformanceTaskGeneratorImpl()
