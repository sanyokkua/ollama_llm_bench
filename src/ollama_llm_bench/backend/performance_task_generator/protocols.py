"""PerformanceTaskGenerator — this module's swap point (spec §1, §2.1)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkTask, PerformanceConfig

__all__: list[str] = ["PerformanceTaskGenerator"]


class PerformanceTaskGenerator(Protocol):
    """Expand a `PerformanceConfig` into a synthetic `BenchmarkTask` grid (spec §1)."""

    def generate(self, config: PerformanceConfig, /) -> tuple[BenchmarkTask, ...]:
        """Fast-synchronous, pure, callable from any thread (spec §9).

        Args:
            config: The validated input/output size matrix and repeat count for
                a `SYNTHETIC` run.

        Returns:
            One `BenchmarkTask` per `(input size x output size x repeat)`
            combination, in deterministic order (spec §3, §5).

        Raises:
            ContractViolationError: Only when `config` carries a value the New
                Benchmark widget should never have produced (spec §8) — never
                raised for a well-formed config.
        """
        ...
