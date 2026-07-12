"""Proves STORY-024-AC-3 — visible_sections returns exactly the non-HIDDEN cells, in order."""

import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import (
    ConfigSection,
    Visibility,
    is_visible,
    visible_sections,
)


@pytest.mark.parametrize("mode", list(RunMode))
def test_visible_sections_are_the_non_hidden_cells(mode: RunMode) -> None:
    """Proves: STORY-024-AC-3

    For every RunMode, visible_sections(mode) returns exactly the set of
    ConfigSection members whose §6.2 cell for that mode is not HIDDEN, in
    ConfigSection declaration order, and includes no HIDDEN-celled section.
    """
    # Act
    result = visible_sections(mode)
    # Assert
    expected = tuple(
        section for section in ConfigSection if is_visible(mode, section) != Visibility.HIDDEN
    )
    assert result == expected
    assert all(is_visible(mode, section) != Visibility.HIDDEN for section in result)


def test_visible_sections_synthetic_excludes_task_files() -> None:
    """Proves: STORY-024-AC-3

    A concrete, spec-grounded example (§10.1): SYNTHETIC hides TASK_FILES and
    EMBEDDING_MODEL_INFO, so neither appears in the returned tuple.
    """
    # Act
    result = visible_sections(RunMode.SYNTHETIC)
    # Assert
    assert ConfigSection.TASK_FILES not in result
    assert ConfigSection.EMBEDDING_MODEL_INFO not in result
    assert ConfigSection.INPUT_SIZES in result
