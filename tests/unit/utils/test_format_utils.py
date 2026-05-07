"""Unit tests for backend/utils/format.py — displayed_score helper."""

import pytest

from ollama_llm_bench.backend.utils.format import displayed_score


class TestDisplayedScoreDecimal:
    def test_typical_value(self) -> None:
        assert displayed_score(0.85, "decimal") == "0.85"

    def test_zero(self) -> None:
        assert displayed_score(0.0, "decimal") == "0.00"

    def test_one(self) -> None:
        assert displayed_score(1.0, "decimal") == "1.00"

    def test_rounds_to_two_decimal_places(self) -> None:
        assert displayed_score(0.333, "decimal") == "0.33"


class TestDisplayedScorePercent:
    def test_typical_value(self) -> None:
        assert displayed_score(0.85, "percent") == "85%"

    def test_zero(self) -> None:
        assert displayed_score(0.0, "percent") == "0%"

    def test_one(self) -> None:
        assert displayed_score(1.0, "percent") == "100%"

    def test_rounds_to_nearest_integer(self) -> None:
        assert displayed_score(0.856, "percent") == "86%"


class TestDisplayedScoreBoth:
    def test_typical_value(self) -> None:
        assert displayed_score(0.85, "both") == "0.85 / 85%"

    def test_zero(self) -> None:
        assert displayed_score(0.0, "both") == "0.00 / 0%"

    def test_one(self) -> None:
        assert displayed_score(1.0, "both") == "1.00 / 100%"


class TestDisplayedScoreFallback:
    def test_unknown_format_falls_back_to_decimal(self) -> None:
        assert displayed_score(0.5, "unknown_format") == "0.50"

    def test_empty_format_falls_back_to_decimal(self) -> None:
        assert displayed_score(0.5, "") == "0.50"

    @pytest.mark.parametrize(
        "fmt",
        ["0_to_1", "DECIMAL", "Percent", "BOTH"],
        ids=["legacy_key", "uppercase_decimal", "capitalized_percent", "uppercase_both"],
    )
    def test_non_matching_case_falls_back_to_decimal(self, fmt: str) -> None:
        assert displayed_score(0.75, fmt) == "0.75"
