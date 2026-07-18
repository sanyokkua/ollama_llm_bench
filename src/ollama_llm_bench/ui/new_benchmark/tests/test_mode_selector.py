"""Unit tests for ``_internal.mode_selector.ModeSelectorWidget`` (STORY-054-AC-1)."""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget


def test_restores_and_persists_last_mode(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-1

    Given the widget initialises with TASKS pre-selected (the caller reads
    ``benchmark.last_mode`` and calls ``set_mode`` before showing), TASKS is the
    selected mode; and selecting GRADED emits ``mode_changed(RunMode.GRADED)``.
    """
    # Arrange
    widget = ModeSelectorWidget()
    qtbot.addWidget(widget)
    widget.set_mode(RunMode.TASKS)
    # Act / Assert (initial restore)
    assert widget.selected_mode == RunMode.TASKS
    # Act (user selects a different mode)
    with qtbot.waitSignal(widget.mode_changed, timeout=1000) as blocker:
        widget.select_mode_for_test(RunMode.GRADED)
    # Assert
    actual_args: list[RunMode] = list(blocker.args)
    assert actual_args == [RunMode.GRADED]
    assert widget.selected_mode == RunMode.GRADED  # type: ignore[comparison-overlap]


def test_set_mode_does_not_emit_mode_changed(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-1

    Programmatic ``set_mode`` (construction-time restore) never emits
    ``mode_changed`` -- only a genuine user selection does, so restoring the
    persisted mode never re-persists it redundantly.
    """
    # Arrange
    widget = ModeSelectorWidget()
    qtbot.addWidget(widget)
    received: list[RunMode] = []
    widget.mode_changed.connect(received.append)
    # Act
    widget.set_mode(RunMode.GRADED)
    # Assert
    assert received == []
    assert widget.selected_mode == RunMode.GRADED
