"""Unit tests for BadgeLabel and HealthDot common widgets."""

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import EvalVerdict, PipelineStage
from ollama_llm_bench.ui.widgets.common.badge_label import BadgeLabel
from ollama_llm_bench.ui.widgets.common.health_dot import HealthDot

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
# BadgeLabel fixtures — function scope; fresh widget per test
# ---------------------------------------------------------------------------


@pytest.fixture
def badge(qapp: QApplication) -> BadgeLabel:
    """Return a fresh BadgeLabel for each test."""
    return BadgeLabel()


# ---------------------------------------------------------------------------
# Group A — BadgeLabel.set_stage
# ---------------------------------------------------------------------------


def test_badge_label_set_stage_initializing_shows_stage_value(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_stage(PipelineStage.INITIALIZING)

    # Assert
    assert badge.text() == PipelineStage.INITIALIZING.value


def test_badge_label_set_stage_finished_shows_stage_value(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_stage(PipelineStage.FINISHED)

    # Assert
    assert badge.text() == PipelineStage.FINISHED.value


def test_badge_label_set_stage_sets_pipeline_stage_property(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_stage(PipelineStage.BENCHMARKING)

    # Assert — QSS property drives styling; inline stylesheet must be empty
    assert badge.property("pipeline_stage") == PipelineStage.BENCHMARKING.name
    assert badge.styleSheet() == ""


# ---------------------------------------------------------------------------
# Group B — BadgeLabel.set_verdict
# ---------------------------------------------------------------------------


def test_badge_label_set_verdict_pass_shows_pass_text(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_verdict(EvalVerdict.PASS)

    # Assert
    assert badge.text() == EvalVerdict.PASS.value


def test_badge_label_set_verdict_fail_shows_fail_text(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_verdict(EvalVerdict.FAIL)

    # Assert
    assert badge.text() == EvalVerdict.FAIL.value


def test_badge_label_set_verdict_unknown_shows_unknown_text(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_verdict(EvalVerdict.UNKNOWN)

    # Assert
    assert badge.text() == EvalVerdict.UNKNOWN.value


# ---------------------------------------------------------------------------
# Group C — BadgeLabel.set_custom
# ---------------------------------------------------------------------------


def test_badge_label_set_custom_shows_provided_text(badge: BadgeLabel) -> None:
    # Arrange / Act
    badge.set_custom("my text", "#FF0000")

    # Assert
    assert badge.text() == "my text"


# ---------------------------------------------------------------------------
# Group D — HealthDot
# ---------------------------------------------------------------------------


@pytest.fixture
def dot(qapp: QApplication) -> HealthDot:
    """Return a fresh HealthDot for each test."""
    return HealthDot()


def test_health_dot_initial_size_is_12x12(dot: HealthDot) -> None:
    # Assert — size is set in __init__ via setFixedSize(12, 12)
    assert dot.width() == 12
    assert dot.height() == 12


def test_health_dot_set_live_sets_health_property(dot: HealthDot) -> None:
    # Arrange / Act
    dot.set_live()

    # Assert
    assert dot.property("health") == "live"


def test_health_dot_set_down_sets_health_property(dot: HealthDot) -> None:
    # Arrange / Act
    dot.set_down()

    # Assert
    assert dot.property("health") == "down"


def test_health_dot_set_unknown_sets_health_property(dot: HealthDot) -> None:
    # Arrange — start from "live" so the transition is exercised
    dot.set_live()

    # Act
    dot.set_unknown()

    # Assert
    assert dot.property("health") == "unknown"


def test_health_dot_noop_when_same_state_does_not_raise(dot: HealthDot) -> None:
    # Arrange — first call transitions to "live"
    dot.set_live()

    # Act — second call is a no-op (same state); must not raise
    dot.set_live()

    # Assert — property unchanged, no exception
    assert dot.property("health") == "live"
