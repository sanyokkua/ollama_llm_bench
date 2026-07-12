"""Public surface for backend/mode_visibility/: is_visible and visible_sections.

Source of truth: docs/v3_specification/11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md
§3 (outputs), §6.1 (section vocabulary), §6.2 (the policy table), §6.3 (the lookup),
§8 (error handling), §9 (threading and concurrency — pure, immutable, built once at
import time, with a startup self-check that fails fast on a missing cell).
"""

from collections.abc import Mapping
from types import MappingProxyType

import icontract

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.mode_visibility.models import ConfigSection, Visibility

__all__: list[str] = ["is_visible", "visible_sections"]

_V = Visibility

POLICY_TABLE: Mapping[ConfigSection, Mapping[RunMode, Visibility]] = MappingProxyType(
    {
        ConfigSection.RUN_MODE_SELECTOR: MappingProxyType(
            {RunMode.SYNTHETIC: _V.VISIBLE, RunMode.TASKS: _V.VISIBLE, RunMode.GRADED: _V.VISIBLE}
        ),
        ConfigSection.TEST_MODELS_PICKER: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.VISIBLE_REQUIRED,
                RunMode.TASKS: _V.VISIBLE_REQUIRED,
                RunMode.GRADED: _V.VISIBLE_REQUIRED,
            }
        ),
        ConfigSection.INPUT_SIZES: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.VISIBLE_REQUIRED,
                RunMode.TASKS: _V.HIDDEN,
                RunMode.GRADED: _V.HIDDEN,
            }
        ),
        ConfigSection.OUTPUT_SIZES: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.VISIBLE_REQUIRED,
                RunMode.TASKS: _V.HIDDEN,
                RunMode.GRADED: _V.HIDDEN,
            }
        ),
        ConfigSection.REPEATS: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.VISIBLE_REQUIRED,
                RunMode.TASKS: _V.HIDDEN,
                RunMode.GRADED: _V.HIDDEN,
            }
        ),
        ConfigSection.TASK_FILES: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.HIDDEN,
                RunMode.TASKS: _V.VISIBLE_REQUIRED,
                RunMode.GRADED: _V.VISIBLE_REQUIRED,
            }
        ),
        ConfigSection.JUDGE_MODEL_PICKER: MappingProxyType(
            {RunMode.SYNTHETIC: _V.VISIBLE, RunMode.TASKS: _V.VISIBLE, RunMode.GRADED: _V.VISIBLE}
        ),
        ConfigSection.EMBEDDING_MODEL_INFO: MappingProxyType(
            {
                RunMode.SYNTHETIC: _V.HIDDEN,
                RunMode.TASKS: _V.HIDDEN,
                RunMode.GRADED: _V.VISIBLE_REQUIRED,
            }
        ),
        ConfigSection.RUN_ANALYSIS_TOGGLE: MappingProxyType(
            {RunMode.SYNTHETIC: _V.VISIBLE, RunMode.TASKS: _V.VISIBLE, RunMode.GRADED: _V.VISIBLE}
        ),
        ConfigSection.ADVANCED_OPTIONS: MappingProxyType(
            {RunMode.SYNTHETIC: _V.VISIBLE, RunMode.TASKS: _V.VISIBLE, RunMode.GRADED: _V.VISIBLE}
        ),
    }
)


def _assert_policy_table_is_total(
    table: Mapping[ConfigSection, Mapping[RunMode, Visibility]],
) -> None:
    """Fail fast if `table` has an undefined (mode, section) cell (§8, §9).

    Iterates the full RunMode x ConfigSection product; a missing cell is a
    maintenance gap (§7), never a runtime condition, so it raises rather than
    silently defaulting.

    Raises:
        ContractViolationError: `table` is missing at least one of the 30 cells.
    """
    missing = [
        f"({mode.value}, {section.value})"
        for section in ConfigSection
        for mode in RunMode
        if section not in table or mode not in table[section]
    ]
    if missing:
        message = f"mode-visibility POLICY_TABLE is missing cells: {', '.join(missing)}"
        raise ContractViolationError(message=message)


_assert_policy_table_is_total(POLICY_TABLE)


@icontract.require(lambda mode: isinstance(mode, RunMode), "mode must be a RunMode member")
@icontract.require(
    lambda section: isinstance(section, ConfigSection),
    "section must be a ConfigSection member — an unknown section indicates a "
    "policy-table maintenance gap (§7), never a runtime condition (§8)",
)
def is_visible(mode: RunMode, section: ConfigSection) -> Visibility:
    """Return the Visibility of `section` when the New Benchmark widget is in `mode` (§6.3).

    Args:
        mode: The run mode currently selected on the New Benchmark widget.
        section: The section or widget whose visibility is being queried.

    Returns:
        The Visibility value for this (mode, section) cell — the lookup is total
        over the full 3x10 product (§5).
    """
    return POLICY_TABLE[section][mode]


@icontract.require(lambda mode: isinstance(mode, RunMode), "mode must be a RunMode member")
@icontract.ensure(
    lambda result, mode: all(is_visible(mode, section) != Visibility.HIDDEN for section in result),
    "every returned section must be non-HIDDEN for mode",
)
def visible_sections(mode: RunMode) -> tuple[ConfigSection, ...]:
    """Return every ConfigSection whose §6.2 cell for `mode` is not HIDDEN (§6.1).

    Args:
        mode: The run mode currently selected on the New Benchmark widget.

    Returns:
        The sections shown in `mode`, in ConfigSection declaration order (a
        stable order — STORY-024-AC-3).
    """
    return tuple(
        section for section in ConfigSection if is_visible(mode, section) != Visibility.HIDDEN
    )
