"""Acceptance tests for STORY-073: run-log search-match highlighting (§8.1)."""

from typing import cast

from PySide6.QtWidgets import QLineEdit, QTextEdit
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import ErrorKind
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_STAGE_CHANGED,
    SIGNAL_TASK_RETRY,
    StageChangedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.backend.log_formatting.testing import FakeLogFormatter
from ollama_llm_bench.ui.progress._internal.log_controller import LogController
from ollama_llm_bench.ui.progress._internal.select import highlight_search_matches
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus
from ollama_llm_bench.ui.progress.tests.test_log_controller import _inference_started
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

# Non-colour placeholder — the architecture scan covers test files too and rejects
# any hex-colour literal. The helper never validates the colour value, and all
# assertions interpolate this token, so a non-colour-shaped value passes both the
# gate and the test.
_HEX = "test-highlight-token"
_EXPECTED_MULTIPLE_OCCURRENCES = 2


def test_highlight_wraps_case_insensitive_match_outside_tags() -> None:
    """Proves: STORY-073-AC-3

    The matched substring is wrapped in a background-coloured span; the match
    is case-insensitive and existing markup tags are never touched.
    """
    line = '<span class="tone-warning">JUDGE</span> · task: t1 judge phase'
    highlighted = highlight_search_matches(line, "judge", highlight_color_hex=_HEX)
    assert '<span class="tone-warning">' in highlighted  # tag intact
    assert f'<span style="background-color: {_HEX}">JUDGE</span>' in highlighted
    assert f'<span style="background-color: {_HEX}">judge</span>' in highlighted


def test_highlight_empty_term_returns_line_unchanged() -> None:
    """Proves: STORY-073-AC-3

    Clearing the search removes every mark — an empty term is a no-op.
    """
    line = '<span class="tone-info">STAGE</span> · benchmarking'
    assert highlight_search_matches(line, "", highlight_color_hex=_HEX) == line


def test_highlight_preserves_escaped_entities() -> None:
    """Proves: STORY-073-AC-3

    Matching happens on visible text: an entity-escaped segment is decoded for
    matching and re-escaped in the output, so entities are never corrupted.
    """
    line = "model: qwen &amp; friends"
    highlighted = highlight_search_matches(line, "qwen & fr", highlight_color_hex=_HEX)
    assert f'<span style="background-color: {_HEX}">qwen &amp; fr</span>' in highlighted


def test_highlight_wraps_multiple_occurrences() -> None:
    """Proves: STORY-073-AC-3

    Multiple occurrences of the search term within the same line are each
    independently wrapped in a background-coloured span.
    """
    line = "judge phase then judge again"
    highlighted = highlight_search_matches(line, "judge", highlight_color_hex=_HEX)
    wrapped_count = highlighted.count(f'<span style="background-color: {_HEX}">judge</span>')
    assert wrapped_count == _EXPECTED_MULTIPLE_OCCURRENCES


def test_highlight_whitespace_only_term_returns_line_unchanged() -> None:
    """Proves: STORY-073-AC-3

    A search term consisting only of whitespace is treated as empty and leaves
    the line unchanged.
    """
    line = '<span class="tone-info">STAGE</span> · benchmarking'
    assert highlight_search_matches(line, "   ", highlight_color_hex=_HEX) == line


def _bind_view_with_log_controller(
    *,
    gateway: FakeProgressGateway,
    event_bus: FakeEventBus,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
    qtbot: QtBot,
) -> tuple[LogController, ProgressView, FakeLogFormatter]:
    """Wire a real ``ProgressView`` (theme-bearing, so ``_search_highlight_hex``
    resolves a real colour) to a real ``LogController`` -- mirrors
    ``test_log_controller.py``'s ``_bind`` helper, plus a theme manager."""
    view = ProgressView(theme_manager=theme_manager, platform_kind=platform_kind)
    qtbot.addWidget(view)
    log_formatter = FakeLogFormatter()
    controller = LogController(gateway=gateway, event_bus=event_bus, log_formatter=log_formatter)
    controller.bind(view)
    return controller, view, log_formatter


def test_search_filters_and_highlights_matches_case_insensitively(
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-073-AC-3

    description.md §8.1: the Run Event Log search box filters visible lines
    **and highlights matches**, case-insensitively. Three lines are appended,
    only two of which contain "judge"/"JUDGE"; typing "JUDGE" into the search
    box hides the third line and wraps every match (regardless of case) in a
    background-coloured span. Clearing the search restores all three lines
    and removes every highlight span.
    """
    # Arrange -- a real view + controller, theme-bearing so the highlight
    # colour resolves to a real hex value, not None.
    _controller, view, log_formatter = _bind_view_with_log_controller(
        gateway=fake_gateway,
        event_bus=fake_event_bus,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
        qtbot=qtbot,
    )
    view.show()

    # Act -- three lines, two containing "judge"/"JUDGE", one not
    log_formatter.next_fragment = '<span class="tone-info">judge phase started</span>'
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    log_formatter.next_fragment = '<span class="tone-warning">JUDGE timed out</span>'
    fake_event_bus.emit(
        SIGNAL_TASK_RETRY,
        TaskRetryEvent(
            run_id=1,
            result_id=1,
            task_id="task-1",
            provider_id="prov-1",
            model_name="model-1",
            attempt=2,
            total_attempts=3,
            reason="Connection refused",
            error_kind=ErrorKind.PROVIDER,
        ),
    )
    log_formatter.next_fragment = '<span class="tone-info">stage advanced</span>'
    fake_event_bus.emit(
        SIGNAL_STAGE_CHANGED,
        StageChangedEvent(run_id=1, stage="inference", stage_index=2, stage_count=5),
    )
    qtbot.wait(100)

    log_body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    search_edit = cast("QLineEdit", view.findChild(QLineEdit, "progress.log.search"))
    assert "judge phase started" in log_body.toPlainText()
    assert "JUDGE timed out" in log_body.toPlainText()
    assert "stage advanced" in log_body.toPlainText()

    # Act -- type the search term
    qtbot.keyClicks(search_edit, "JUDGE")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    qtbot.wait(100)

    # Assert -- only the two matching lines remain, and a highlight span exists
    plain_text = log_body.toPlainText()
    assert "judge phase started" in plain_text
    assert "JUDGE timed out" in plain_text
    assert "stage advanced" not in plain_text
    assert "background-color" in log_body.toHtml()

    # Act -- clear the search term
    search_edit.clear()
    qtbot.wait(100)

    # Assert -- all three lines are back, no highlight span remains
    plain_text = log_body.toPlainText()
    assert "judge phase started" in plain_text
    assert "JUDGE timed out" in plain_text
    assert "stage advanced" in plain_text
    assert "background-color" not in log_body.toHtml()
