"""Proves STORY-024-AC-4 — an unknown section raises, and the self-check catches a missing cell."""

import icontract
import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.mode_visibility import ConfigSection, is_visible
from ollama_llm_bench.backend.mode_visibility.api import POLICY_TABLE, _assert_policy_table_is_total


def test_is_visible_with_non_config_section_raises_violation_error() -> None:
    """Proves: STORY-024-AC-4

    is_visible called with a value that is not a ConfigSection member raises
    an icontract ViolationError (a programmer-error signal per §8) and never
    returns a silent HIDDEN default.
    """
    # Act / Assert
    with pytest.raises(icontract.errors.ViolationError):
        is_visible(RunMode.SYNTHETIC, "not-a-config-section")  # type: ignore[arg-type]


def test_is_visible_with_non_run_mode_raises_violation_error() -> None:
    """Proves: STORY-024-AC-4

    is_visible called with a value that is not a RunMode member raises an
    icontract ViolationError rather than proceeding with an invalid key.
    """
    # Act / Assert
    with pytest.raises(icontract.errors.ViolationError):
        is_visible("not-a-run-mode", ConfigSection.ADVANCED_OPTIONS)  # type: ignore[arg-type]


def test_self_check_passes_on_the_real_policy_table() -> None:
    """Proves: STORY-024-AC-4

    The self-check that already ran at module-import time is independently
    callable on the real POLICY_TABLE and raises nothing.
    """
    # Act / Assert (no exception)
    _assert_policy_table_is_total(POLICY_TABLE)


def test_self_check_raises_on_a_table_missing_one_cell() -> None:
    """Proves: STORY-024-AC-4

    Given the table has a cell removed, the self-check raises a
    ContractViolationError with a clear missing-cell message rather than
    letting the application discover the gap mid-interaction (§8, §9).
    """
    # Arrange
    broken_table = {section: dict(modes) for section, modes in POLICY_TABLE.items()}
    del broken_table[ConfigSection.ADVANCED_OPTIONS][RunMode.GRADED]

    # Act / Assert
    with pytest.raises(ContractViolationError, match="graded, advanced_options"):
        _assert_policy_table_is_total(broken_table)
