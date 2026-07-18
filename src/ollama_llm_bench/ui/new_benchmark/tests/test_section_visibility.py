"""Unit tests for ``_internal.section_visibility`` (STORY-054-AC-2)."""

import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection, visible_sections
from ollama_llm_bench.ui.new_benchmark._internal.section_visibility import visible_section_set


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
