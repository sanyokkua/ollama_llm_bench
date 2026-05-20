"""Unit tests for SummaryTableModel and DetailedTableModel."""

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.ui.models.detailed_table_model import DetailedTableModel
from ollama_llm_bench.ui.models.summary_table_model import SummaryTableModel

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
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


def _make_avg_item(
    model_name: str = "test-model",
    avg_time_ms: float = 1000.0,
    avg_tokens_per_second: float = 20.0,
    avg_score: float = 0.8,
    pass_rate: float = 0.75,
    avg_ttft_ms: float | None = None,
) -> AvgSummaryTableItem:
    return AvgSummaryTableItem(
        model_name=model_name,
        avg_time_ms=avg_time_ms,
        avg_tokens_per_second=avg_tokens_per_second,
        avg_score=avg_score,
        pass_rate=pass_rate,
        avg_ttft_ms=avg_ttft_ms,
    )


def _make_summary_item(
    model_name: str = "test-model",
    task_id: str = "task1",
    task_status: str = "COMPLETED",
    time_ms: int = 1500,
    tokens: int = 100,
    tokens_per_second: float = 10.0,
    score: float = 0.9,
    cosine_similarity: float | None = None,
    resolution_layer: str = "layer1",
    score_reason: str = "good answer",
    error_message: str = "",
) -> SummaryTableItem:
    return SummaryTableItem(
        model_name=model_name,
        task_id=task_id,
        task_status=task_status,
        time_ms=time_ms,
        tokens=tokens,
        tokens_per_second=tokens_per_second,
        score=score,
        cosine_similarity=cosine_similarity,
        resolution_layer=resolution_layer,
        score_reason=score_reason,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# SummaryTableModel tests
# ---------------------------------------------------------------------------


def test_summary_model_row_count(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    items = [_make_avg_item(model_name=f"m{i}") for i in range(3)]

    # Act
    model.update_data(items)

    # Assert
    assert model.rowCount() == 3


def test_summary_model_column_count(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()

    # Act
    count = model.columnCount()

    # Assert
    assert count == 7


def test_summary_model_header_data(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()

    # Act
    header = model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)

    # Assert
    assert header == "MODEL"


def test_summary_model_display_role_time(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(avg_time_ms=2500.0)])

    # Act
    result = model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result == "2.50"


def test_summary_model_user_role_time(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(avg_time_ms=2500.0)])

    # Act
    result = model.data(model.index(0, 1), Qt.ItemDataRole.UserRole)

    # Assert
    assert result == pytest.approx(2.5)


def test_summary_model_display_role_pass_rate(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(pass_rate=0.75)])

    # Act
    result = model.data(model.index(0, 4), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result == "75.0%"


def test_summary_model_ttft_none_display(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(avg_ttft_ms=None)])

    # Act
    result = model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result == "—"


def test_summary_model_ttft_none_user_role(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(avg_ttft_ms=None)])

    # Act
    result = model.data(model.index(0, 5), Qt.ItemDataRole.UserRole)

    # Assert
    assert result is None


def test_summary_model_update_data_replaces_rows(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item(model_name=f"m{i}") for i in range(3)])

    # Act
    model.update_data([_make_avg_item(model_name="only")])

    # Assert
    assert model.rowCount() == 1


def test_summary_model_invalid_index_returns_none(qapp: QApplication) -> None:
    # Arrange
    model = SummaryTableModel()
    model.update_data([_make_avg_item()])

    # Act
    result = model.data(QModelIndex(), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# DetailedTableModel tests
# ---------------------------------------------------------------------------


def test_detailed_model_row_count(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    items = [_make_summary_item(task_id=f"task{i}") for i in range(5)]

    # Act
    model.update_data(items)

    # Assert
    assert model.rowCount() == 5


def test_detailed_model_column_count(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()

    # Act
    count = model.columnCount()

    # Assert
    assert count == 11


def test_detailed_model_cosine_none_display(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(cosine_similarity=None)])

    # Act
    result = model.data(model.index(0, 7), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result == "—"


def test_detailed_model_cosine_none_user_role(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(cosine_similarity=None)])

    # Act
    result = model.data(model.index(0, 7), Qt.ItemDataRole.UserRole)

    # Assert
    assert result is None


def test_detailed_model_tokens_user_role_is_float(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(tokens=100)])

    # Act
    result = model.data(model.index(0, 4), Qt.ItemDataRole.UserRole)

    # Assert
    assert result == pytest.approx(100.0)


def test_detailed_model_text_alignment_numeric_col(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item()])

    # Act
    result = model.data(model.index(0, 3), Qt.ItemDataRole.TextAlignmentRole)

    # Assert
    assert result == Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def test_detailed_model_text_alignment_text_col(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item()])

    # Act
    result = model.data(model.index(0, 0), Qt.ItemDataRole.TextAlignmentRole)

    # Assert
    assert result == Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def test_detailed_model_error_column_returns_error_message(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(error_message="inference timeout")])

    # Act
    result = model.data(model.index(0, 10), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result == "inference timeout"


def test_detailed_model_error_column_returns_none_when_empty(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(error_message="")])

    # Act
    result = model.data(model.index(0, 10), Qt.ItemDataRole.DisplayRole)

    # Assert
    assert result is None


def test_detailed_model_foreground_role_returns_error_color_when_error(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(error_message="bad json")])

    # Act
    result = model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole)

    # Assert
    assert result == QColor("#e05252")


def test_detailed_model_foreground_role_returns_none_when_no_error(qapp: QApplication) -> None:
    # Arrange
    model = DetailedTableModel()
    model.update_data([_make_summary_item(error_message="")])

    # Act
    result = model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole)

    # Assert
    assert result is None
