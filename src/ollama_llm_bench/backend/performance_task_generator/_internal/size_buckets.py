"""The fixed size-bucket table (spec §2.3) and its numeric-to-label lookup.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md``
§2.3 — the five fixed named size buckets the New Benchmark widget offers, keyed by
their approximate target token count.
"""

from types import MappingProxyType
from typing import Final

from ollama_llm_bench.backend.errors import ContractViolationError

__all__: list[str] = ["SIZE_BUCKETS", "_bucket_label"]

SIZE_BUCKETS: Final[MappingProxyType[int, str]] = MappingProxyType(
    {
        64: "tiny",
        256: "small",
        1024: "medium",
        4096: "large",
        16384: "xlarge",
    }
)


def _bucket_label(size: int, /) -> str:
    """Map a numeric target token count to its fixed bucket label (spec §2.3).

    Args:
        size: A numeric value from ``PerformanceConfig.input_sizes`` or
            ``.output_sizes``.

    Returns:
        The bucket label matching ``size``, e.g. ``"medium"`` for ``1024``.

    Raises:
        ContractViolationError: `size` matches no defined bucket (spec §8) — the
            New Benchmark widget should never have produced this value.
    """
    try:
        return SIZE_BUCKETS[size]
    except KeyError as exc:
        message = (
            f"PerformanceConfig size {size} has no matching size bucket "
            "(known: 64, 256, 1024, 4096, 16384)"
        )
        raise ContractViolationError(message=message) from exc
