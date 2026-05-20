"""Unit tests for the extended helpers in backend/utils/format.py."""

import pytest

from ollama_llm_bench.backend.utils.filename_utils import default_export_filename
from ollama_llm_bench.backend.utils.format import format_attempt_durations, format_progress_label


class TestFormatProgressLabel:
    def test_typical_progress(self) -> None:
        assert format_progress_label(5, 10) == "5 / 10 (50%)"

    def test_zero_completed(self) -> None:
        assert format_progress_label(0, 10) == "0 / 10 (0%)"

    def test_all_completed(self) -> None:
        assert format_progress_label(10, 10) == "10 / 10 (100%)"

    def test_zero_total(self) -> None:
        assert format_progress_label(0, 0) == "0 / 0 (0%)"

    def test_negative_total(self) -> None:
        assert format_progress_label(0, -1) == "0 / 0 (0%)"

    def test_rounds_down(self) -> None:
        result = format_progress_label(1, 3)
        assert "33" in result

    def test_clamps_to_100(self) -> None:
        result = format_progress_label(200, 10)
        assert "(100%)" in result


class TestFormatAttemptDurations:
    def test_single_attempt(self) -> None:
        result = format_attempt_durations([5000.0])
        assert result == "Attempt 1: 5s · Total: 5s"

    def test_two_attempts(self) -> None:
        result = format_attempt_durations([3000.0, 7000.0])
        assert result == "Attempt 1: 3s · Attempt 2: 7s · Total: 10s"

    def test_empty_list(self) -> None:
        assert format_attempt_durations([]) == ""

    def test_integer_durations(self) -> None:
        result = format_attempt_durations((2000, 4000))  # type: ignore[arg-type]
        assert "Attempt 1: 2s" in result
        assert "Attempt 2: 4s" in result
        assert "Total: 6s" in result

    def test_sub_second_rounds_to_zero(self) -> None:
        result = format_attempt_durations([500.0])
        assert "Attempt 1: 0s" in result


class TestDefaultExportFilename:
    def test_contains_report_type_and_ext(self) -> None:
        result = default_export_filename("my run", "summary", "csv")
        assert result.endswith("_summary.csv")

    def test_sanitizes_illegal_chars(self) -> None:
        result = default_export_filename("run: 1/2", "detail", "md")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "/" not in result

    def test_contains_timestamp_pattern(self) -> None:
        import re

        result = default_export_filename("run", "summary", "csv")
        assert re.search(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}", result)

    @pytest.mark.parametrize(
        "ext",
        ["csv", "md", "json"],
        ids=["csv", "md", "json"],
    )
    def test_extension_appended(self, ext: str) -> None:
        result = default_export_filename("run", "report", ext)
        assert result.endswith(f".{ext}")
