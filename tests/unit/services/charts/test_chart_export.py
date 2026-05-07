"""Unit tests for ChartFrame._caption_text and _format_filter_summary.

These tests use a lightweight stub object — no QApplication required.
"""

from __future__ import annotations

from freezegun import freeze_time

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
)
from ollama_llm_bench.ui.widgets.panels.result.charts.chart_frame import ChartFrame


def _make_result(*, model_name: str = "model_a", task_category: str = "reasoning") -> BenchmarkResult:
    return BenchmarkResult(
        model_name=model_name,
        task_id="t1",
        task_category=task_category,
        status=BenchmarkResultStatus.COMPLETED,
        has_inference_error=False,
        has_judge_error=False,
    )


class _CaptionHost:
    """Minimal host that satisfies the attribute reads inside _caption_text and _format_filter_summary."""

    def __init__(self, chart_name: str, filter_state: dict, results: list) -> None:
        self._chart_name = chart_name
        self._filter_state = filter_state
        self._results = results

    def _caption_text(self) -> str:
        return ChartFrame._caption_text(self)  # type: ignore[arg-type]

    def _format_filter_summary(self) -> str:
        return ChartFrame._format_filter_summary(self)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _caption_text
# ---------------------------------------------------------------------------


def test_caption_text_contains_chart_name() -> None:
    host = _CaptionHost("My Chart", {}, [])
    assert host._caption_text().startswith("My Chart")


@freeze_time("2025-06-15 09:30:00")
def test_caption_text_contains_timestamp() -> None:
    host = _CaptionHost("Any", {}, [])
    assert "2025-06-15 09:30" in host._caption_text()


def test_caption_text_separator_is_middot() -> None:
    results = [_make_result(model_name="a"), _make_result(model_name="b")]
    filter_state: dict = {"model_name": frozenset({"a"}), "log_scale": True}
    host = _CaptionHost("Chart", filter_state, results)
    text = host._caption_text()
    # At least chart name + summary + timestamp separated by " · "
    parts = text.split(" · ")
    assert len(parts) >= 3


# ---------------------------------------------------------------------------
# _format_filter_summary
# ---------------------------------------------------------------------------


def test_format_filter_summary_empty_when_no_filters() -> None:
    host = _CaptionHost("Chart", {}, [])
    assert host._format_filter_summary() == ""


def test_format_filter_summary_includes_model_fraction_when_filtered() -> None:
    results = [_make_result(model_name="a"), _make_result(model_name="b")]
    filter_state: dict = {"model_name": frozenset({"a"})}
    host = _CaptionHost("Chart", filter_state, results)
    assert "1/2 models" in host._format_filter_summary()


def test_format_filter_summary_no_fraction_when_all_models_included() -> None:
    results = [_make_result(model_name="a"), _make_result(model_name="b")]
    filter_state: dict = {"model_name": frozenset({"a", "b"})}
    host = _CaptionHost("Chart", filter_state, results)
    assert "models" not in host._format_filter_summary()


def test_format_filter_summary_includes_category_fraction_when_filtered() -> None:
    results = [_make_result(task_category="math"), _make_result(task_category="code")]
    filter_state: dict = {"task_category": frozenset({"math"})}
    host = _CaptionHost("Chart", filter_state, results)
    assert "1/2 categories" in host._format_filter_summary()


def test_format_filter_summary_includes_log_scale_when_active() -> None:
    host = _CaptionHost("Chart", {"log_scale": True}, [])
    assert "log scale" in host._format_filter_summary()


def test_format_filter_summary_no_log_scale_when_inactive() -> None:
    host = _CaptionHost("Chart", {"log_scale": False}, [])
    assert "log scale" not in host._format_filter_summary()
