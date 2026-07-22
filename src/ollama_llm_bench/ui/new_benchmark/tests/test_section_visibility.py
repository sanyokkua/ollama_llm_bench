"""Unit tests for ``_internal.section_visibility`` (STORY-054-AC-2, STORY-071-AC-6)."""

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection, visible_sections
from ollama_llm_bench.ui.new_benchmark._internal.section_visibility import visible_section_set
from ollama_llm_bench.ui.new_benchmark.testing import FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.new_benchmark.tests.test_validation_and_start import _build_widget
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager


class _RealBackedPolicy:
    """Wraps the real ``backend.mode_visibility.visible_sections`` -- never hand-faked,
    since AC-2 must check against the actual policy table."""

    def visible_sections(self, mode: RunMode) -> tuple[ConfigSection, ...]:
        return visible_sections(mode)


# The story's own AC-2 table, expressed against the full ConfigSection vocabulary
# (10_MODE_VISIBILITY_POLICY.md §6.2): Performance Matrix == INPUT_SIZES/OUTPUT_SIZES/REPEATS,
# Embedding status row == EMBEDDING_MODEL_INFO.
@pytest.mark.parametrize(
    ("mode", "expected_visible"),
    [
        (
            RunMode.SYNTHETIC,
            frozenset(
                {
                    ConfigSection.RUN_MODE_SELECTOR,
                    ConfigSection.TEST_MODELS_PICKER,
                    ConfigSection.INPUT_SIZES,
                    ConfigSection.OUTPUT_SIZES,
                    ConfigSection.REPEATS,
                    ConfigSection.JUDGE_MODEL_PICKER,
                    ConfigSection.RUN_ANALYSIS_TOGGLE,
                    ConfigSection.ADVANCED_OPTIONS,
                }
            ),
        ),
        (
            RunMode.TASKS,
            frozenset(
                {
                    ConfigSection.RUN_MODE_SELECTOR,
                    ConfigSection.TEST_MODELS_PICKER,
                    ConfigSection.TASK_FILES,
                    ConfigSection.JUDGE_MODEL_PICKER,
                    ConfigSection.RUN_ANALYSIS_TOGGLE,
                    ConfigSection.ADVANCED_OPTIONS,
                }
            ),
        ),
        (
            RunMode.GRADED,
            frozenset(
                {
                    ConfigSection.RUN_MODE_SELECTOR,
                    ConfigSection.TEST_MODELS_PICKER,
                    ConfigSection.TASK_FILES,
                    ConfigSection.JUDGE_MODEL_PICKER,
                    ConfigSection.EMBEDDING_MODEL_INFO,
                    ConfigSection.RUN_ANALYSIS_TOGGLE,
                    ConfigSection.ADVANCED_OPTIONS,
                }
            ),
        ),
    ],
)
def test_visible_sections_match_policy_per_mode(
    mode: RunMode, expected_visible: frozenset[ConfigSection]
) -> None:
    """Proves: STORY-054-AC-2

    For each RunMode, the widget's visible-section set equals the Mode Visibility
    Policy's set for that mode -- including sections (Performance Matrix, Judge,
    Embedding status row, Advanced Options, Start) whose real content is stubbed
    in this story.
    """
    # Arrange
    policy = _RealBackedPolicy()
    # Act
    result = visible_section_set(mode=mode, policy=policy)
    # Assert
    assert result == expected_visible


@pytest.mark.parametrize(
    ("mode", "expected_visible"),
    [
        (RunMode.SYNTHETIC, True),
        (RunMode.TASKS, False),
        (RunMode.GRADED, False),
    ],
    ids=["synthetic_visible", "tasks_removed", "graded_removed"],
)
def test_performance_matrix_visibility_per_mode(  # noqa: PLR0913  # parametrize axes plus
    # four construction fixtures
    mode: RunMode,
    expected_visible: bool,  # noqa: FBT001  # parametrize tuple element
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-071-AC-6

    The Input Sizes, Output Sizes, and Repeats sections (one combined widget
    mapped from all three ConfigSection keys) are visible in SYNTHETIC and
    removed from the layout in TASKS and GRADED.
    """
    # Arrange
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=()),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    # Act
    view.mode_selector.select_mode_for_test(mode)
    # Assert
    assert view.performance_matrix_section.isVisibleTo(view) is expected_visible
