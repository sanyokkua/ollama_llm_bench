"""Tests for MultiCheckFilterButton widget."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.widgets.common.multi_check_filter_button import MultiCheckFilterButton

# ---------------------------------------------------------------------------
# QApplication — module scope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPTS_5 = ["a", "b", "c", "d", "e"]
_COUNTS_5 = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}


def _make_btn(qapp: QApplication, label: str = "Models") -> MultiCheckFilterButton:
    return MultiCheckFilterButton(label=label)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_initial_state_all_selected(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)

    # Act
    btn.set_options(_OPTS_5, _COUNTS_5)

    # Assert
    assert btn.selected() == frozenset({"a", "b", "c", "d", "e"})
    assert "All (5)" in btn.text()


def test_button_text_partial_selection(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(_OPTS_5, _COUNTS_5)

    # Act
    btn._on_item_toggled("d", False)  # type: ignore[attr-defined]
    btn._on_item_toggled("e", False)  # type: ignore[attr-defined]

    # Assert
    assert "3 of 5" in btn.text()


def test_button_text_empty_selection(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(_OPTS_5, _COUNTS_5)

    # Act
    btn._clear_all()  # type: ignore[attr-defined]

    # Assert
    assert "None — empty" in btn.text()


def test_uncheck_emits_selection_changed_on_menu_close(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(_OPTS_5, _COUNTS_5)
    received: list[frozenset[str]] = []
    btn.selection_changed.connect(lambda fs: received.append(fs))

    # Act
    btn._on_item_toggled("a", False)  # type: ignore[attr-defined]
    btn._on_item_toggled("b", False)  # type: ignore[attr-defined]
    btn._on_menu_closed()  # type: ignore[attr-defined]

    # Assert
    assert len(received) == 1
    assert received[0] == frozenset({"c", "d", "e"})


def test_select_all_restores_full_set(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(_OPTS_5, _COUNTS_5)
    btn._clear_all()  # type: ignore[attr-defined]

    # Act
    btn._select_all()  # type: ignore[attr-defined]

    # Assert
    assert btn.selected() == frozenset({"a", "b", "c", "d", "e"})


def test_invert_flips_all_states(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(["a", "b", "c", "d"], {"a": 1, "b": 1, "c": 1, "d": 1})
    # Uncheck "a" and "b" via the checkbox widget (triggers stateChanged → _on_item_toggled)
    cbs = btn._checkboxes  # type: ignore[attr-defined]
    cbs["a"].setChecked(False)
    cbs["b"].setChecked(False)

    # Act
    btn._invert()  # type: ignore[attr-defined]

    # Assert — a and b were unchecked, now checked; c and d were checked, now unchecked
    assert "a" in btn.selected()
    assert "b" in btn.selected()
    assert "c" not in btn.selected()
    assert "d" not in btn.selected()


def test_search_filters_visibility_only(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(["model_a", "model_b", "other"], {"model_a": 1, "model_b": 1, "other": 1})

    # Act
    btn._on_search_changed("mo")  # type: ignore[attr-defined]

    # Assert — "other" is in the search-hidden set; "model_a" and "model_b" are not
    hidden: set[str] = btn._search_hidden  # type: ignore[attr-defined]
    assert "other" in hidden
    assert "model_a" not in hidden
    assert "model_b" not in hidden

    # Closing menu emits all originally selected items (visibility does not deselect)
    received: list[frozenset[str]] = []
    btn.selection_changed.connect(lambda fs: received.append(fs))
    btn._on_menu_closed()  # type: ignore[attr-defined]
    assert received[0] == frozenset({"model_a", "model_b", "other"})


def test_options_change_preserves_intersection(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(["a", "b", "c"], {"a": 1, "b": 1, "c": 1})
    btn._on_item_toggled("c", False)  # type: ignore[attr-defined]

    # Act — new options overlap only on "b"
    btn.set_options(["b", "c", "d"], {"b": 1, "c": 1, "d": 1})

    # Assert
    assert btn.selected() == frozenset({"b"})


def test_options_change_empty_intersection_defaults_to_all(qapp: QApplication) -> None:
    # Arrange
    btn = _make_btn(qapp)
    btn.set_options(["a", "b"], {"a": 1, "b": 1})

    # Act — completely disjoint new option set
    btn.set_options(["x", "y"], {"x": 1, "y": 1})

    # Assert — defaults to all-selected when intersection is empty
    assert btn.selected() == frozenset({"x", "y"})
