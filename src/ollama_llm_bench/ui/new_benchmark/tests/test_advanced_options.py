"""Unit tests for ``_internal.advanced_options.AdvancedOptionsSectionWidget``
(STORY-055-AC-3) and the DD-47 completeness rule.
"""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.backend.settings import PER_RUN_OVERRIDABLE
from ollama_llm_bench.ui.new_benchmark._internal.advanced_options import (
    _CONTROL_KEYS,
    AdvancedOptionsSectionWidget,
)

_ANALYSIS_TOGGLE_KEY: SettingKey = "feature.judge_run_analysis_enabled"
_CHANGED_KEY: SettingKey = "benchmark.min_timeout_seconds"


def _make_widget() -> AdvancedOptionsSectionWidget:
    return AdvancedOptionsSectionWidget(initial_values={})


def test_only_changed_overrides_are_carried(qtbot: QtBot) -> None:
    """Proves: STORY-055-AC-3

    Given the checkbox is checked and the user changed exactly one control from
    its seeded value, then ``dirty_keys`` reports exactly that one changed key.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    widget._activation_box.setChecked(True)
    # Act
    widget._rows[_CHANGED_KEY].set_text("50")
    # Assert
    assert widget.dirty_keys == frozenset({_CHANGED_KEY})


def test_unchecking_discards_dirty_keys(qtbot: QtBot) -> None:
    """Proves: STORY-055-AC-3

    Per description.md §4.7 ("Unchecking ... discards the per-run edits, so the
    run reverts to the global values"), ``dirty_keys`` reports an empty set once
    the activation checkbox is unchecked, even though a control was edited while
    it was checked -- the widget must actually clear its diff on uncheck, not
    merely collapse the section visually.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    widget._activation_box.setChecked(True)
    widget._rows[_CHANGED_KEY].set_text("50")
    # Act
    widget._activation_box.setChecked(False)
    # Assert
    assert widget.dirty_keys == frozenset()


def test_control_keys_cover_every_per_run_overridable_key_except_analysis_toggle() -> None:
    """Proves: STORY-055 Definition of done

    The DD-47 completeness rule: ``_CONTROL_KEYS`` covers every
    ``PER_RUN_OVERRIDABLE`` key except the form's own primary analysis toggle,
    which ``_internal/judge_section.py`` owns.
    """
    # Act / Assert
    assert frozenset(_CONTROL_KEYS) == PER_RUN_OVERRIDABLE - {_ANALYSIS_TOGGLE_KEY}
