"""Colocated unit tests for MultiCheckFilterButton (STORY-051-AC-3)."""

from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.shared import make_multi_check_filter_button
from ollama_llm_bench.ui.shared._internal.multi_check_filter_button import (
    MultiCheckFilterButtonWidget,
)
from ollama_llm_bench.ui.shared.models import FilterSelectionChanged


def test_toggle_updates_count_label_and_emits_selection(qapp: QApplication) -> None:
    """Proves: STORY-051-AC-3

    Given a MultiCheckFilterButton built over a set of options, when the user toggles an
    option, then the button's label reflects the current checked count and the button emits
    its selection-changed signal carrying the current checked option set.
    """
    widget = make_multi_check_filter_button(label="Status", options=("PASS", "FAIL", "PENDING"))
    assert isinstance(widget, MultiCheckFilterButtonWidget)
    received: list[FilterSelectionChanged] = []
    widget.selection_changed.connect(received.append)

    widget.toggle_option("PASS")

    assert widget.text() == "Status (1)"
    assert received == [FilterSelectionChanged(selected_keys=("PASS",))]
