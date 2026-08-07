"""Colocated unit tests for the Providers tab's RowActionsDelegate (STORY-099-AC-3)."""

from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QApplication, QTableView, QWidget
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_table_models import ProviderTableRow, make_providers_table_model
from ollama_llm_bench.backend.domain import ProviderTestStatus, ProviderType
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.row_actions_delegate import (
    COL_ENABLED,
    RowActionsDelegate,
)
from ollama_llm_bench.ui.theme import PlatformKind

if TYPE_CHECKING:
    from collections.abc import Iterable


def _row() -> ProviderTableRow:
    return ProviderTableRow(
        provider_id="00000000-0000-4000-8000-000000000001",
        label="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        base_url_display="(default)",
        auth_badge="none",
        health=ProviderTestStatus.READY,
        enabled=True,
    )


def test_providers_delegate_creates_no_per_row_widget(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-099-AC-3

    The delegate paints the Enabled checkbox plus hover-revealed Test/More
    glyphs directly; it never instantiates a per-row QWidget, keeping the
    Providers table virtualised.
    """
    # Arrange
    table = QTableView()
    model = make_providers_table_model(rows=(_row(), _row()))
    table.setModel(model)
    delegate = RowActionsDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    table.setItemDelegateForColumn(COL_ENABLED, delegate)
    qtbot.addWidget(table)
    children_before = len(list(cast("Iterable[QWidget]", table.viewport().findChildren(QWidget))))

    # Act
    with qtbot.waitExposed(table):
        table.show()
    table.viewport().update()
    qtbot.wait(50)

    # Assert
    children_after = list(cast("Iterable[QWidget]", table.viewport().findChildren(QWidget)))
    assert len(children_after) == children_before
