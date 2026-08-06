"""Proves: STORY-098-AC-3

The shared table-model base can answer Qt.ItemDataRole.AccessibleTextRole
when constructed with an accessible-text callback
(08_ACCESSIBILITY_FLOOR.md #7-accessible-names).
"""

from PySide6.QtCore import Qt

from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel


def test_frozen_row_table_model_answers_accessible_text_role_when_configured() -> None:
    """Proves: STORY-098-AC-3

    A model constructed with an accessible_text callback answers
    AccessibleTextRole by delegating to that callback.
    """
    # Arrange
    model: _FrozenRowTableModel[str] = _FrozenRowTableModel(
        headers=("Col",),
        cell_value=lambda row, _col: row,
        rows=("row-0",),
        accessible_text=lambda row, _col: f"accessible: {row}",
    )
    index = model.index(0, 0)

    # Act
    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    # Assert
    assert result == "accessible: row-0"


def test_frozen_row_table_model_returns_none_for_accessible_text_role_when_unconfigured() -> None:
    """Proves: STORY-098-AC-3

    A model constructed with no accessible_text callback answers None for
    AccessibleTextRole, keeping the three existing concrete subclasses'
    behaviour unchanged.
    """
    # Arrange
    model: _FrozenRowTableModel[str] = _FrozenRowTableModel(
        headers=("Col",), cell_value=lambda row, _col: row, rows=("row-0",)
    )
    index = model.index(0, 0)

    # Act
    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    # Assert
    assert result is None
