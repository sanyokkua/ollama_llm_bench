"""Unit tests for the shared gate-busy indicator strip (STORY-097)."""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.shared import make_gate_busy_indicator

_GENERATE_ANALYSIS_MESSAGE = "An inference is currently in flight — please wait."


def test_gate_busy_indicator_carries_the_pinned_identity(qtbot: QtBot) -> None:
    """The shared strip reports the registry's pinned objectName, accessible name, and
    tooltip regardless of which sentence the caller supplies."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert (strip.objectName(), strip.accessibleName(), strip.toolTip()) == (
        "gate_busy_indicator",
        "Inference in flight — controls temporarily disabled",
        "An inference is in flight; please wait.",
    )


def test_gate_busy_indicator_shows_the_callers_message(qtbot: QtBot) -> None:
    """The visible sentence is the caller's, because each surface's wording is pinned by
    that surface's own spec -- only the identity attributes are shared."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert strip.text() == _GENERATE_ANALYSIS_MESSAGE


def test_gate_busy_indicator_starts_hidden(qtbot: QtBot) -> None:
    """The strip is mounted permanently and revealed only while the gate is held, so it
    must not be visible at construction."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert not strip.isVisible()
