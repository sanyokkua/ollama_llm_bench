"""A configurable fake PerformanceTaskGenerator for downstream module tests."""

from ollama_llm_bench.backend.domain import BenchmarkTask, PerformanceConfig
from ollama_llm_bench.backend.performance_task_generator._internal.generator import (
    _PerformanceTaskGeneratorImpl,
)

__all__: list[str] = ["FakePerformanceTaskGenerator"]


class FakePerformanceTaskGenerator:
    """A recording fake that delegates to the real generator by default.

    Records every `config` passed to `generate` in `recorded_configs`, for
    downstream-module test assertions. Delegates to the real, stateless
    `_PerformanceTaskGeneratorImpl` by default so downstream tests get real,
    correct synthetic tasks; `set_tasks` overrides the return value when a
    test wants canned data instead.
    """

    def __init__(self) -> None:
        self._real = _PerformanceTaskGeneratorImpl()
        self._override: tuple[BenchmarkTask, ...] | None = None
        self.recorded_configs: list[PerformanceConfig] = []

    def generate(self, config: PerformanceConfig, /) -> tuple[BenchmarkTask, ...]:
        """Record `config` and return the configured or real task tuple."""
        self.recorded_configs.append(config)
        if self._override is not None:
            return self._override
        return self._real.generate(config)

    def set_tasks(self, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Test helper: force every subsequent `generate` call to return `tasks`."""
        self._override = tasks
