"""Unit tests for ollama_llm_bench.backend.utils.time_utils.format_compact_duration."""

import pytest

from ollama_llm_bench.backend.utils.time_utils import format_compact_duration


@pytest.mark.parametrize(
    ("total_ms", "expected"),
    [
        (0.0, "0s"),
        (999.9, "0s"),
        (1000.0, "1s"),
        (59999.0, "59s"),
        (60000.0, "1m 0s"),
        (65000.0, "1m 5s"),
        (3599000.0, "59m 59s"),
        (3600000.0, "1h 0m 0s"),
        (10143000.0, "2h 49m 3s"),
        (-500.0, "0s"),
    ],
    ids=[
        "zero",
        "sub_second",
        "one_second",
        "under_one_minute",
        "exactly_one_minute",
        "one_minute_five_seconds",
        "under_one_hour",
        "exactly_one_hour",
        "multi_hour",
        "negative_clamped",
    ],
)
def test_format_compact_duration(total_ms: float, expected: str) -> None:
    # Act
    result = format_compact_duration(total_ms)

    # Assert
    assert result == expected
