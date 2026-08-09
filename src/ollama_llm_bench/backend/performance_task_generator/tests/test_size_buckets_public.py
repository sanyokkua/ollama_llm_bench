"""Colocated tests for the published size-bucket table (STORY-092-AC-1).

Every import here names the package root, never
``backend.performance_task_generator._internal.*`` — that import path is itself the
assertion: it is what proves the table sits on the module's public surface and is
reachable by the New Benchmark widget without breaching ``import-linter``'s
"Module internals are private" contract.
"""

from typing import Any

import pytest

from ollama_llm_bench.backend.performance_task_generator import SIZE_BUCKETS

# The §2.3 table restated independently of the implementation — an assertion is only
# worth running when its expectation is derived from the spec, not from the code.
_CANONICAL_TABLE: dict[int, str] = {
    64: "tiny",
    256: "small",
    1024: "medium",
    4096: "large",
    16384: "xlarge",
}


def test_public_bucket_table_is_the_canonical_mapping() -> None:
    """Proves: STORY-092-AC-1

    Read through the generator's public surface, the size-bucket table maps
    exactly 64 -> "tiny", 256 -> "small", 1024 -> "medium", 4096 -> "large",
    16384 -> "xlarge", and contains no other entry.
    """
    # Arrange / Act
    published = dict(SIZE_BUCKETS)
    # Assert
    assert published == _CANONICAL_TABLE


def test_public_bucket_table_is_immutable() -> None:
    """Proves: STORY-092-AC-1

    Publishing the table must not hand a caller something it can mutate: the
    published mapping rejects a write at runtime and is unchanged afterwards.
    """
    # Arrange -- bound through ``Any`` so the deliberately illegal write reaches the
    # runtime instead of being stopped by mypy; the runtime rejection is the point.
    writable: Any = SIZE_BUCKETS
    # Act / Assert
    with pytest.raises(TypeError):
        writable[999] = "huge"
    assert dict(SIZE_BUCKETS) == _CANONICAL_TABLE
