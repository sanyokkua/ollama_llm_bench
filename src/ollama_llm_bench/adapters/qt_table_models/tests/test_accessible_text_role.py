"""Proves: STORY-098-AC-3

The shared table-model base can answer Qt.ItemDataRole.AccessibleTextRole
when constructed with an accessible-text callback
(08_ACCESSIBILITY_FLOOR.md #7-accessible-names).
"""

from PySide6.QtCore import Qt

from ollama_llm_bench.adapters.qt_table_models import ProviderTableRow, make_providers_table_model
from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel
from ollama_llm_bench.backend.domain import ProviderTestStatus, ProviderType


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


def test_providers_enabled_cell_exposes_state_and_actions_as_accessible_text() -> None:
    """Proves: STORY-099-AC-3

    The Providers table's Enabled column answers AccessibleTextRole with the
    row's enabled state in words plus the Test/More actions available on it,
    since the checkbox/Test/More glyphs are delegate-painted, not real
    widgets, so they have no QWidget to carry an accessible name themselves.
    """
    # Arrange
    row = ProviderTableRow(
        provider_id="00000000-0000-4000-8000-000000000001",
        label="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        base_url_display="(default)",
        auth_badge="none",
        health=ProviderTestStatus.READY,
        enabled=True,
    )
    model = make_providers_table_model(rows=(row,))
    index = model.index(0, 5)

    # Act
    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    # Assert
    assert result == "Ollama (local): Enabled. Test connection and More actions available."
