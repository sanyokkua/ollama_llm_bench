"""Proves STORY-024-AC-2 — every (mode, section) cell matches the exact §6.2 spec table."""

import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection, Visibility, is_visible

_V = Visibility
_M = RunMode

# Exactly the §6.2 table in docs/v3_specification/11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md.
_EXPECTED_CELLS: dict[tuple[RunMode, ConfigSection], Visibility] = {
    (_M.SYNTHETIC, ConfigSection.RUN_MODE_SELECTOR): _V.VISIBLE,
    (_M.TASKS, ConfigSection.RUN_MODE_SELECTOR): _V.VISIBLE,
    (_M.GRADED, ConfigSection.RUN_MODE_SELECTOR): _V.VISIBLE,
    (_M.SYNTHETIC, ConfigSection.TEST_MODELS_PICKER): _V.VISIBLE_REQUIRED,
    (_M.TASKS, ConfigSection.TEST_MODELS_PICKER): _V.VISIBLE_REQUIRED,
    (_M.GRADED, ConfigSection.TEST_MODELS_PICKER): _V.VISIBLE_REQUIRED,
    (_M.SYNTHETIC, ConfigSection.INPUT_SIZES): _V.VISIBLE_REQUIRED,
    (_M.TASKS, ConfigSection.INPUT_SIZES): _V.HIDDEN,
    (_M.GRADED, ConfigSection.INPUT_SIZES): _V.HIDDEN,
    (_M.SYNTHETIC, ConfigSection.OUTPUT_SIZES): _V.VISIBLE_REQUIRED,
    (_M.TASKS, ConfigSection.OUTPUT_SIZES): _V.HIDDEN,
    (_M.GRADED, ConfigSection.OUTPUT_SIZES): _V.HIDDEN,
    (_M.SYNTHETIC, ConfigSection.REPEATS): _V.VISIBLE_REQUIRED,
    (_M.TASKS, ConfigSection.REPEATS): _V.HIDDEN,
    (_M.GRADED, ConfigSection.REPEATS): _V.HIDDEN,
    (_M.SYNTHETIC, ConfigSection.TASK_FILES): _V.HIDDEN,
    (_M.TASKS, ConfigSection.TASK_FILES): _V.VISIBLE_REQUIRED,
    (_M.GRADED, ConfigSection.TASK_FILES): _V.VISIBLE_REQUIRED,
    (_M.SYNTHETIC, ConfigSection.JUDGE_MODEL_PICKER): _V.VISIBLE,
    (_M.TASKS, ConfigSection.JUDGE_MODEL_PICKER): _V.VISIBLE,
    (_M.GRADED, ConfigSection.JUDGE_MODEL_PICKER): _V.VISIBLE,
    (_M.SYNTHETIC, ConfigSection.EMBEDDING_MODEL_INFO): _V.HIDDEN,
    (_M.TASKS, ConfigSection.EMBEDDING_MODEL_INFO): _V.HIDDEN,
    (_M.GRADED, ConfigSection.EMBEDDING_MODEL_INFO): _V.VISIBLE_REQUIRED,
    (_M.SYNTHETIC, ConfigSection.RUN_ANALYSIS_TOGGLE): _V.VISIBLE,
    (_M.TASKS, ConfigSection.RUN_ANALYSIS_TOGGLE): _V.VISIBLE,
    (_M.GRADED, ConfigSection.RUN_ANALYSIS_TOGGLE): _V.VISIBLE,
    (_M.SYNTHETIC, ConfigSection.ADVANCED_OPTIONS): _V.VISIBLE,
    (_M.TASKS, ConfigSection.ADVANCED_OPTIONS): _V.VISIBLE,
    (_M.GRADED, ConfigSection.ADVANCED_OPTIONS): _V.VISIBLE,
}

_EXPECTED_CELL_COUNT = 30


def test_expected_cells_table_has_thirty_entries() -> None:
    """Proves: STORY-024-AC-2

    Sanity guard: the expected-value fixture above must itself cover all
    30 cells, or the parametrized check below would pass vacuously.
    """
    # Assert
    assert len(_EXPECTED_CELLS) == _EXPECTED_CELL_COUNT


@pytest.mark.parametrize(
    ("mode", "section", "expected"),
    [(mode, section, visibility) for (mode, section), visibility in _EXPECTED_CELLS.items()],
)
def test_each_cell_matches_the_spec_table(
    mode: RunMode, section: ConfigSection, expected: Visibility
) -> None:
    """Proves: STORY-024-AC-2

    Each (mode, section) cell resolves to exactly the Visibility value in the
    §6.2 table.
    """
    # Act
    result = is_visible(mode, section)
    # Assert
    assert result == expected
