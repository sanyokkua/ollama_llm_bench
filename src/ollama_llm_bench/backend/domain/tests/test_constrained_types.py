"""Tests proving every reusable constrained type in §3 enforces its bound.

``msgspec.Meta`` constraints are validated at decode/convert time, not at direct
``ClassName(...)`` construction (standard, documented msgspec behaviour — see the
``msgspec-domain-modeling`` skill and ``16_Engineering_Standards/03_CODING_STANDARDS.md``).
Each case therefore round-trips a value through ``msgspec.convert(..., type=X)`` to actually
exercise the ``msgspec.Meta`` bound.
"""

from typing import Any

import msgspec
import pytest

from ollama_llm_bench.backend.domain.models import (
    CosineScore,
    CosineThreshold,
    DurationMs,
    ModelNameStr,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    ProviderIdStr,
    RepeatCount,
    RetryCount,
    TaskIdStr,
    TimeoutSeconds,
)

_VALID_UUID4 = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"

# (constrained_type, in_bound_value, out_of_bound_value)
_CASES: tuple[tuple[Any, Any, Any], ...] = (
    (ProviderIdStr, _VALID_UUID4, "not-a-uuid"),
    (ModelNameStr, "a", ""),
    (TaskIdStr, "a", ""),
    (NonNegativeFloat, 0.0, -0.1),
    (PositiveFloat, 0.1, 0.0),
    (NonEmptyStr, "a", ""),
    (CosineScore, 1.0, 1.1),
    (CosineThreshold, 0.0, -0.1),
    (RetryCount, 10, 11),
    (TimeoutSeconds, 3600, 3601),
    (PositiveInt, 1, 0),
    (NonNegativeInt, 0, -1),
    (DurationMs, 0, -1),
    (RepeatCount, 50, 51),
)

_IDS = [
    "ProviderIdStr",
    "ModelNameStr",
    "TaskIdStr",
    "NonNegativeFloat",
    "PositiveFloat",
    "NonEmptyStr",
    "CosineScore",
    "CosineThreshold",
    "RetryCount",
    "TimeoutSeconds",
    "PositiveInt",
    "NonNegativeInt",
    "DurationMs",
    "RepeatCount",
]


@pytest.mark.parametrize(("constrained_type", "in_bound", "out_of_bound"), _CASES, ids=_IDS)
def test_constrained_type_bounds_enforced_at_construction(
    constrained_type: Any, in_bound: Any, out_of_bound: Any
) -> None:
    """Proves: STORY-001-AC-1

    For every constrained type in §3, decoding a value inside its declared
    ``msgspec.Meta`` bound succeeds and decoding a value outside the bound raises
    ``msgspec.ValidationError``.
    """
    # Act
    decoded = msgspec.convert(in_bound, type=constrained_type)

    # Assert
    assert decoded == in_bound
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(out_of_bound, type=constrained_type)
