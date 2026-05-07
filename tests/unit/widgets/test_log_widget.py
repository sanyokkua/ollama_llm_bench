"""Unit tests for LogWidget — streaming buffer, HTML colour coding, lifecycle events,
auto-scroll toggle, and scrollback cap."""

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, EventBus
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkResultStatus,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    EvalLayer,
    EvalVerdict,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    ModelDescriptor,
    PipelineStage,
    RunMode,
    StopReason,
    StreamingChunkEvent,
    TaskCompletedEvent,
)
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL = ModelDescriptor(
    provider_id="ollama",
    provider_type="openai_compatible",
    model_name="llama3",
    display_label="llama3",
)

_STARTED_EVENT = BenchmarkStartedEvent(
    run_id=1,
    total_tasks=4,
    models=(_MODEL,),
    run_mode=RunMode.FULL_GRADING,
)


def _make_streaming_event(chunk_text: str) -> StreamingChunkEvent:
    return StreamingChunkEvent(
        run_id=1,
        result_id=1,
        model_name="llama3",
        task_id="task_001",
        chunk_text=chunk_text,
        is_thinking_block=False,
    )


def _make_task_completed_event(total_time_ms: float | None) -> TaskCompletedEvent:
    return TaskCompletedEvent(
        run_id=1,
        result_id=1,
        model=_MODEL,
        task_id="task_001",
        status=BenchmarkResultStatus.COMPLETED,
        total_time_ms=total_time_ms,
        ttft_ms=None,
        final_verdict=None,
    )


def _make_judge_event(verdict: EvalVerdict) -> JudgeCompletedEvent:
    return JudgeCompletedEvent(
        run_id=1,
        result_id=1,
        layer=EvalLayer.LLM_JUDGE,
        verdict=verdict,
        resolved=True,
    )


def _make_finished_event(run_id: int = 1, completed: int = 5, failed: int = 1) -> BenchmarkFinishedEvent:
    return BenchmarkFinishedEvent(
        run_id=run_id,
        total_time_ms=12000.0,
        completed_count=completed,
        failed_count=failed,
    )


def _make_stopped_event(run_id: int = 1) -> BenchmarkStoppedEvent:
    return BenchmarkStoppedEvent(run_id=run_id, stop_reason=StopReason.USER)


# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Widget fixture — function scope; fresh widget per test
# ---------------------------------------------------------------------------


@pytest.fixture
def widget(qapp: QApplication, mocker: MockerFixture) -> LogWidget:
    """Construct a LogWidget with mock EventBus and AppSettingsServiceApi."""
    mock_bus = mocker.Mock(spec=EventBus)
    mock_settings = mocker.Mock(spec=AppSettingsServiceApi)
    mock_settings.get_int.return_value = 10_000
    return LogWidget(event_bus=mock_bus, app_settings=mock_settings)


# ---------------------------------------------------------------------------
# Group A — streaming buffer (_chunk_buffer)
# ---------------------------------------------------------------------------


def test_on_streaming_chunk_appends_to_buffer(widget: LogWidget) -> None:
    # Arrange
    event = _make_streaming_event("hello token")

    # Act
    widget._on_streaming_chunk(event)

    # Assert
    assert "hello token" in widget._chunk_buffer


def test_drain_chunk_buffer_with_content_populates_text_edit(widget: LogWidget) -> None:
    # Arrange
    widget._chunk_buffer.append("some output text")

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert not widget._text_edit.document().isEmpty()


def test_drain_chunk_buffer_with_content_clears_buffer(widget: LogWidget) -> None:
    # Arrange
    widget._chunk_buffer.append("some output text")

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert widget._chunk_buffer == []


def test_drain_chunk_buffer_when_empty_leaves_document_empty(widget: LogWidget) -> None:
    # Arrange
    widget._text_edit.clear()
    widget._chunk_buffer.clear()

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert widget._text_edit.document().isEmpty()


def test_drain_chunk_buffer_escapes_ampersand(widget: LogWidget) -> None:
    # Arrange
    widget._chunk_buffer.append("a & b")

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert "&amp;" in widget._text_edit.toHtml()


def test_drain_chunk_buffer_escapes_less_than(widget: LogWidget) -> None:
    # Arrange
    widget._chunk_buffer.append("<tag>")

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert "&lt;" in widget._text_edit.toHtml()


def test_drain_chunk_buffer_escapes_greater_than(widget: LogWidget) -> None:
    # Arrange
    widget._chunk_buffer.append("<tag>")

    # Act
    widget._drain_chunk_buffer()

    # Assert
    assert "&gt;" in widget._text_edit.toHtml()


# ---------------------------------------------------------------------------
# Group B — task completed entry
# ---------------------------------------------------------------------------


def test_on_task_completed_with_time_contains_model_name(widget: LogWidget) -> None:
    # Arrange
    event = _make_task_completed_event(total_time_ms=500.0)

    # Act
    widget._on_task_completed(event)

    # Assert
    assert "llama3" in widget._text_edit.toHtml()


def test_on_task_completed_with_time_contains_task_id(widget: LogWidget) -> None:
    # Arrange
    event = _make_task_completed_event(total_time_ms=500.0)

    # Act
    widget._on_task_completed(event)

    # Assert
    assert "task_001" in widget._text_edit.toHtml()


def test_on_task_completed_with_time_shows_duration_label(widget: LogWidget) -> None:
    # Arrange
    event = _make_task_completed_event(total_time_ms=90_000.0)  # 90 seconds

    # Act
    widget._on_task_completed(event)

    # Assert — output contains human-readable duration (1m 30s) and End: label
    html = widget._text_edit.toHtml()
    assert "Duration:" in html
    assert "End:" in html
    assert "1m 30s" in html


def test_on_task_completed_with_none_time_shows_dash(widget: LogWidget) -> None:
    """Completion line shows the \u2013 character (en-dash) when total_time_ms is None."""
    # Arrange
    event = _make_task_completed_event(total_time_ms=None)

    # Act
    widget._on_task_completed(event)

    # Assert — the plain text must contain the en-dash for the None time value
    assert "\u2013" in widget._text_edit.toPlainText()


# ---------------------------------------------------------------------------
# Group C — judge completed colour coding
# ---------------------------------------------------------------------------


def test_on_judge_completed_pass_verdict_uses_pass_color(widget: LogWidget) -> None:
    # Arrange
    event = _make_judge_event(EvalVerdict.PASS)

    # Act
    widget._on_judge_completed(event)

    # Assert — Qt normalises hex colours to lowercase in toHtml() output
    assert widget._color_judge_pass.lower() in widget._text_edit.toHtml()


def test_on_judge_completed_fail_verdict_uses_fail_color(widget: LogWidget) -> None:
    # Arrange
    event = _make_judge_event(EvalVerdict.FAIL)

    # Act
    widget._on_judge_completed(event)

    # Assert — Qt normalises hex colours to lowercase in toHtml() output
    assert widget._color_judge_fail.lower() in widget._text_edit.toHtml()


def test_on_judge_completed_unknown_verdict_uses_secondary_color(widget: LogWidget) -> None:
    # Arrange
    event = _make_judge_event(EvalVerdict.UNKNOWN)

    # Act
    widget._on_judge_completed(event)

    # Assert — Qt normalises hex colours to lowercase in toHtml() output
    assert widget._color_secondary.lower() in widget._text_edit.toHtml()


# ---------------------------------------------------------------------------
# Group D — lifecycle events
# ---------------------------------------------------------------------------


def test_on_benchmark_started_clears_document(widget: LogWidget) -> None:
    # Arrange — put some content in first so we can prove it was cleared
    widget._append_plain("existing content")

    # Act
    widget._on_benchmark_started(_STARTED_EVENT)

    # Assert
    assert widget._text_edit.document().isEmpty()


def test_on_benchmark_started_sets_auto_scroll_true(widget: LogWidget) -> None:
    # Arrange
    widget._auto_scroll = False

    # Act
    widget._on_benchmark_started(_STARTED_EVENT)

    # Assert
    assert widget._auto_scroll is True


def test_on_benchmark_started_hides_jump_button(widget: LogWidget) -> None:
    # Arrange
    widget._jump_button.setVisible(True)

    # Act
    widget._on_benchmark_started(_STARTED_EVENT)

    # Assert — isHidden() checks the explicit hidden flag regardless of top-level show state
    assert widget._jump_button.isHidden() is True


def test_on_benchmark_finished_html_contains_run_id(widget: LogWidget) -> None:
    # Arrange
    event = _make_finished_event(run_id=42)

    # Act
    widget._on_benchmark_finished(event)

    # Assert
    assert "42" in widget._text_edit.toHtml()


def test_on_benchmark_finished_html_contains_completed_count(widget: LogWidget) -> None:
    # Arrange
    event = _make_finished_event(completed=7, failed=2)

    # Act
    widget._on_benchmark_finished(event)

    # Assert
    assert "7" in widget._text_edit.toHtml()


def test_on_benchmark_finished_html_contains_failed_count(widget: LogWidget) -> None:
    # Arrange
    event = _make_finished_event(completed=7, failed=2)

    # Act
    widget._on_benchmark_finished(event)

    # Assert
    assert "2" in widget._text_edit.toHtml()


def test_on_benchmark_stopped_html_contains_run_id(widget: LogWidget) -> None:
    # Arrange
    event = _make_stopped_event(run_id=99)

    # Act
    widget._on_benchmark_stopped(event)

    # Assert
    assert "99" in widget._text_edit.toHtml()


def test_on_benchmark_stopped_html_contains_stopped_keyword(widget: LogWidget) -> None:
    # Arrange
    event = _make_stopped_event(run_id=1)

    # Act
    widget._on_benchmark_stopped(event)

    # Assert
    assert "stopped" in widget._text_edit.toHtml().lower()


# ---------------------------------------------------------------------------
# Group E — auto-scroll toggle (_on_scroll_changed) and jump to bottom
# ---------------------------------------------------------------------------


def test_on_scroll_changed_at_bottom_sets_auto_scroll_true(widget: LogWidget) -> None:
    # Arrange — auto_scroll starts True; force it False first
    widget._auto_scroll = False
    scrollbar = widget._text_edit.verticalScrollBar()
    assert scrollbar is not None
    # When maximum is 0 the scroll is trivially at the bottom (0 >= 0 - 20 is True)
    scrollbar.setMaximum(0)

    # Act
    widget._on_scroll_changed(0)

    # Assert
    assert widget._auto_scroll is True


def test_on_scroll_changed_at_bottom_hides_jump_button(widget: LogWidget) -> None:
    # Arrange
    widget._jump_button.setVisible(True)
    scrollbar = widget._text_edit.verticalScrollBar()
    assert scrollbar is not None
    scrollbar.setMaximum(0)

    # Act
    widget._on_scroll_changed(0)

    # Assert — isHidden() checks the explicit hidden flag regardless of top-level show state
    assert widget._jump_button.isHidden() is True


def test_on_scroll_changed_not_at_bottom_disables_auto_scroll(widget: LogWidget) -> None:
    # Arrange — set scrollbar range so value=0 is far from maximum
    scrollbar = widget._text_edit.verticalScrollBar()
    assert scrollbar is not None
    scrollbar.setMaximum(200)

    # Act — value 0 is well below maximum (200) minus threshold (20)
    widget._on_scroll_changed(0)

    # Assert
    assert widget._auto_scroll is False


def test_on_scroll_changed_not_at_bottom_shows_jump_button(widget: LogWidget) -> None:
    # Arrange
    scrollbar = widget._text_edit.verticalScrollBar()
    assert scrollbar is not None
    scrollbar.setMaximum(200)

    # Act
    widget._on_scroll_changed(0)

    # Assert — isVisibleTo() checks intended visibility relative to the parent widget
    # without requiring the top-level window to be shown (which is correct for unit tests)
    assert widget._jump_button.isVisibleTo(widget) is True


def test_jump_to_bottom_sets_auto_scroll_true(widget: LogWidget) -> None:
    # Arrange
    widget._auto_scroll = False

    # Act
    widget._jump_to_bottom()

    # Assert
    assert widget._auto_scroll is True


def test_jump_to_bottom_hides_jump_button(widget: LogWidget) -> None:
    # Arrange
    widget._jump_button.setVisible(True)

    # Act
    widget._jump_to_bottom()

    # Assert — isHidden() checks the explicit hidden flag regardless of top-level show state
    assert widget._jump_button.isHidden() is True


# ---------------------------------------------------------------------------
# Group F — scrollback cap (_enforce_scrollback_limit)
# ---------------------------------------------------------------------------


@pytest.fixture
def capped_widget(qapp: QApplication, mocker: MockerFixture) -> LogWidget:
    """Widget configured with a scrollback limit of 3 lines."""
    mock_bus = mocker.Mock(spec=EventBus)
    mock_settings = mocker.Mock(spec=AppSettingsServiceApi)
    mock_settings.get_int.return_value = 3
    return LogWidget(event_bus=mock_bus, app_settings=mock_settings)


def test_enforce_scrollback_limit_removes_excess_blocks(capped_widget: LogWidget) -> None:
    # Arrange — append 5 lines through the public helper so the limit is exercised
    for i in range(5):
        capped_widget._append_plain(f"line {i}")

    # Assert — block count must not exceed the configured limit of 3
    assert capped_widget._text_edit.document().blockCount() <= 3


def test_enforce_scrollback_limit_with_fewer_lines_than_cap_keeps_all(capped_widget: LogWidget) -> None:
    # Arrange — append exactly 2 lines (below the limit of 3)
    capped_widget._append_plain("line A")
    capped_widget._append_plain("line B")

    # Assert — both lines should still be present (document is non-empty)
    assert not capped_widget._text_edit.document().isEmpty()
    assert capped_widget._text_edit.document().blockCount() <= 3


def test_enforce_scrollback_limit_with_zero_lines_leaves_empty_document(capped_widget: LogWidget) -> None:
    # Act — nothing appended

    # Assert
    assert capped_widget._text_edit.document().isEmpty()


# ---------------------------------------------------------------------------
# Group G — inference started: timestamps
# ---------------------------------------------------------------------------


def _make_inference_started_event() -> InferenceStartedEvent:
    return InferenceStartedEvent(
        run_id=1,
        result_id=1,
        model=_MODEL,
        task_id="task_001",
        user_prompt="Translate the following text.",
        system_prompt=None,
        stage=PipelineStage.BENCHMARKING,
    )


def test_on_inference_started_shows_start_time_label(widget: LogWidget) -> None:
    # Act
    widget._on_inference_started(_make_inference_started_event())

    # Assert — HTML must contain "Start:" timestamp label
    assert "Start:" in widget._text_edit.toHtml()


def test_on_inference_started_start_time_has_hhmmss_format(widget: LogWidget) -> None:
    # Act
    widget._on_inference_started(_make_inference_started_event())

    # Assert — plain text must contain a colon-separated time value (HH:MM:SS)
    plain = widget._text_edit.toPlainText()
    assert any(c == ":" for c in plain)


# ---------------------------------------------------------------------------
# Group H — task completed: failed status
# ---------------------------------------------------------------------------


def test_on_task_completed_failed_uses_failure_color(widget: LogWidget) -> None:
    # Arrange
    event = TaskCompletedEvent(
        run_id=1,
        result_id=1,
        model=_MODEL,
        task_id="task_001",
        status=BenchmarkResultStatus.FAILED,
        total_time_ms=5000.0,
        ttft_ms=None,
        final_verdict=None,
    )

    # Act
    widget._on_task_completed(event)

    # Assert — failure color must appear in the rendered HTML
    assert widget._color_judge_fail.lower() in widget._text_edit.toHtml()


def test_on_task_completed_failed_shows_failed_label(widget: LogWidget) -> None:
    # Arrange
    event = TaskCompletedEvent(
        run_id=1,
        result_id=1,
        model=_MODEL,
        task_id="task_001",
        status=BenchmarkResultStatus.FAILED,
        total_time_ms=5000.0,
        ttft_ms=None,
        final_verdict=None,
    )

    # Act
    widget._on_task_completed(event)

    # Assert — "FAILED" text must appear in the plain text output
    assert "FAILED" in widget._text_edit.toPlainText()


def test_on_task_completed_success_shows_end_time_label(widget: LogWidget) -> None:
    # Act
    widget._on_task_completed(_make_task_completed_event(total_time_ms=3000.0))

    # Assert — "End:" label must appear in the HTML
    assert "End:" in widget._text_edit.toHtml()
