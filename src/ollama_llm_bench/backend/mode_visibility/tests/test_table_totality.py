"""Proves STORY-024-AC-1 — is_visible is total over the full RunMode x ConfigSection product."""

import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection, Visibility, is_visible

_ALL_CELLS = [(mode, section) for mode in RunMode for section in ConfigSection]
_PRODUCT_SIZE = 30  # 3 RunMode x 10 ConfigSection


def test_full_product_has_thirty_cells() -> None:
    """Proves: STORY-024-AC-1

    Sanity guard for the parametrized check below: RunMode x ConfigSection is
    exactly 3 x 10 = 30 pairs, so the totality check below is not vacuous.
    """
    # Assert
    assert len(_ALL_CELLS) == _PRODUCT_SIZE


@pytest.mark.parametrize(("mode", "section"), _ALL_CELLS)
def test_policy_table_is_total_over_the_product(mode: RunMode, section: ConfigSection) -> None:
    """Proves: STORY-024-AC-1

    For every (mode, section) in the full RunMode x ConfigSection Cartesian
    product, is_visible(mode, section) returns a defined Visibility value with
    no exception — the lookup is total over all 30 cells.
    """
    # Act
    result = is_visible(mode, section)
    # Assert
    assert isinstance(result, Visibility)
