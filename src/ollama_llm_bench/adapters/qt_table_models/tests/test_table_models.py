"""Colocated unit tests for adapters/qt_table_models (STORY-046)."""

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtTest import QAbstractItemModelTester
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_table_models import (
    DetailsTableRow,
    ProviderTableRow,
    SummaryTableRow,
    make_details_table_model,
    make_providers_table_model,
    make_summary_table_model,
)
from ollama_llm_bench.backend.domain import ProviderTestStatus, ProviderType

if TYPE_CHECKING:
    from ollama_llm_bench.adapters.qt_table_models._internal.summary_model import (
        _SummaryTableModel,
    )

_SUMMARY_HEADERS = ("Provider", "Model", "Pass Rate")
_SUMMARY_ROWS = (
    SummaryTableRow(cells=("ollama", "llama3", "80%")),
    SummaryTableRow(cells=("openai", "gpt-4o", "95%")),
)

_DETAILS_HEADERS = ("Task", "Verdict")
_DETAILS_ROWS = (
    DetailsTableRow(result_id=1, cells=("task-1", "PASS")),
    DetailsTableRow(result_id=2, cells=("task-2", "FAIL")),
)

_PROVIDER_ROWS = (
    ProviderTableRow(
        provider_id="0" * 8 + "-" + "0" * 4 + "-4" + "0" * 3 + "-8" + "0" * 3 + "-" + "0" * 12,
        label="Local Ollama",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        base_url_display="(default)",
        auth_badge="none",
        health=ProviderTestStatus.READY,
        enabled=True,
    ),
)


def _make_model(kind: str) -> QAbstractTableModel:
    if kind == "summary":
        return make_summary_table_model(headers=_SUMMARY_HEADERS, rows=_SUMMARY_ROWS)
    if kind == "details":
        return make_details_table_model(headers=_DETAILS_HEADERS, rows=_DETAILS_ROWS)
    return make_providers_table_model(rows=_PROVIDER_ROWS)


def _expected_row_count(kind: str) -> int:
    return {"summary": len(_SUMMARY_ROWS), "details": len(_DETAILS_ROWS), "providers": 1}[kind]


def _expected_column_count(kind: str) -> int:
    return {"summary": len(_SUMMARY_HEADERS), "details": len(_DETAILS_HEADERS), "providers": 6}[
        kind
    ]


def _expected_cell(kind: str, row: int, column: int) -> str:
    if kind == "summary":
        return _SUMMARY_ROWS[row].cells[column]
    if kind == "details":
        return _DETAILS_ROWS[row].cells[column]
    provider_row = _PROVIDER_ROWS[row]
    return (
        provider_row.health.value,
        provider_row.label,
        provider_row.provider_type.value,
        provider_row.base_url_display,
        provider_row.auth_badge,
        str(provider_row.enabled),
    )[column]


_CELL_CASES: tuple[tuple[str, int, int], ...] = tuple(
    (kind, row, column)
    for kind, n_rows, n_columns in (
        ("summary", len(_SUMMARY_ROWS), len(_SUMMARY_HEADERS)),
        ("details", len(_DETAILS_ROWS), len(_DETAILS_HEADERS)),
        ("providers", len(_PROVIDER_ROWS), 6),
    )
    for row in range(n_rows)
    for column in range(n_columns)
)


@pytest.mark.parametrize("kind", ["summary", "details", "providers"])
def test_row_and_column_counts_per_model(kind: str) -> None:
    """Proves: STORY-046-AC-1

    Given a fixed row collection, rowCount() equals the number of rows and
    columnCount() equals that table's column count.
    """
    # Arrange
    model = _make_model(kind)
    # Act / Assert
    assert model.rowCount() == _expected_row_count(kind)
    assert model.columnCount() == _expected_column_count(kind)


@pytest.mark.parametrize("kind,row,column", _CELL_CASES)
def test_cell_data_matches_row_field(kind: str, row: int, column: int) -> None:
    """Proves: STORY-046-AC-1

    For each (model kind, row, column) triple, data(index, DisplayRole) returns
    the value of the corresponding row field.
    """
    # Arrange
    model = _make_model(kind)
    index = model.index(row, column)
    # Act / Assert
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == _expected_cell(kind, row, column)


@pytest.mark.parametrize("kind", ["summary", "details", "providers"])
def test_each_model_satisfies_qt_model_contract(kind: str, qtbot: QtBot) -> None:
    """Proves: STORY-046-AC-2

    Wrapping each model in QAbstractItemModelTester raises on any model-contract
    violation; constructing the tester and exercising the model must not raise.
    """
    # Arrange
    model = _make_model(kind)
    # Act
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    # Assert
    assert tester.model() is model


def test_set_rows_performs_atomic_model_reset(qtbot: QtBot) -> None:
    """Proves: STORY-046-AC-3

    Supplying a new row collection via set_rows performs a begin/endResetModel
    cycle and the model subsequently reports the new rows.
    """
    # Arrange
    # cast: the public factory intentionally returns the opaque QAbstractTableModel
    # type (project-structure.md's public-surface rule); set_rows is this module's
    # documented reset method, defined on the concrete _FrozenRowTableModel subclass.
    model = cast(
        "_SummaryTableModel",
        make_summary_table_model(headers=_SUMMARY_HEADERS, rows=_SUMMARY_ROWS),
    )
    new_headers = ("Provider", "Model")
    new_rows = (SummaryTableRow(cells=("anthropic", "claude")),)
    with qtbot.waitSignal(model.modelReset, timeout=1000):
        # Act
        model.set_rows(headers=new_headers, rows=new_rows)
    # Assert
    assert model.rowCount() == 1
    assert model.columnCount() == len(new_headers)
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "anthropic"
