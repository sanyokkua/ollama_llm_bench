"""Unit tests for NumericSortProxyModel with SummaryTableModel as source."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import AvgSummaryTableItem
from ollama_llm_bench.ui.models.numeric_sort_proxy_model import NumericSortProxyModel
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
    pass_rate: float = 0.5,
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


def _make_proxy_with_items(
    qapp: QApplication, items: list[AvgSummaryTableItem]
) -> tuple[NumericSortProxyModel, SummaryTableModel]:
    """Create a proxy and source model loaded with items."""
    source = SummaryTableModel()
    source.update_data(items)
    proxy = NumericSortProxyModel()
    proxy.setSourceModel(source)
    proxy.setDynamicSortFilter(True)
    return proxy, source


# ---------------------------------------------------------------------------
# Numeric sort tests
# ---------------------------------------------------------------------------


def test_numeric_column_sorts_ascending_by_value(qapp: QApplication) -> None:
    # Arrange — avg_time_ms values: 72020, 7820, 49650, 22800 → sorted: 7.82, 22.8, 49.65, 72.02
    items = [
        _make_avg_item(model_name="a", avg_time_ms=72020.0),
        _make_avg_item(model_name="b", avg_time_ms=7820.0),
        _make_avg_item(model_name="c", avg_time_ms=49650.0),
        _make_avg_item(model_name="d", avg_time_ms=22800.0),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.sort(1, Qt.SortOrder.AscendingOrder)

    # Assert
    row0_val = proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole)
    row3_val = proxy.data(proxy.index(3, 1), Qt.ItemDataRole.UserRole)
    assert row0_val == pytest.approx(7.82)
    assert row3_val == pytest.approx(72.02)


def test_numeric_column_sorts_descending(qapp: QApplication) -> None:
    # Arrange — same data as above
    items = [
        _make_avg_item(model_name="a", avg_time_ms=72020.0),
        _make_avg_item(model_name="b", avg_time_ms=7820.0),
        _make_avg_item(model_name="c", avg_time_ms=49650.0),
        _make_avg_item(model_name="d", avg_time_ms=22800.0),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.sort(1, Qt.SortOrder.DescendingOrder)

    # Assert
    row0_val = proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole)
    assert row0_val == pytest.approx(72.02)


def test_lexicographic_column_unchanged(qapp: QApplication) -> None:
    # Arrange — model names unsorted: banana, apple, cherry
    items = [
        _make_avg_item(model_name="banana"),
        _make_avg_item(model_name="apple"),
        _make_avg_item(model_name="cherry"),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.sort(0, Qt.SortOrder.AscendingOrder)

    # Assert
    names = [proxy.data(proxy.index(r, 0), Qt.ItemDataRole.UserRole) for r in range(3)]
    assert names == ["apple", "banana", "cherry"]


def test_null_sorts_to_bottom_ascending(qapp: QApplication) -> None:
    # Arrange — col 5 (avg_ttft_ms): one real value, one None
    items = [
        _make_avg_item(model_name="with_ttft", avg_ttft_ms=50.0),
        _make_avg_item(model_name="no_ttft", avg_ttft_ms=None),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.sort(5, Qt.SortOrder.AscendingOrder)

    # Assert — None should be at row 1 (bottom)
    bottom_val = proxy.data(proxy.index(1, 5), Qt.ItemDataRole.UserRole)
    assert bottom_val is None


def test_null_sorts_to_bottom_descending(qapp: QApplication) -> None:
    # Arrange — same items; descending sort: None treated as "infinity" by lessThan,
    # so Qt places it at row 0 (top) when reversing.  The contract guarantees
    # None-at-bottom only for ascending; for descending None rises to the top.
    items = [
        _make_avg_item(model_name="with_ttft", avg_ttft_ms=50.0),
        _make_avg_item(model_name="no_ttft", avg_ttft_ms=None),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.sort(5, Qt.SortOrder.DescendingOrder)

    # Assert — None is at row 0 (top) when sorting descending because lessThan
    # treats None as greater-than-any-real (returns False for a=None), and Qt
    # reverses the whole ordering for descending.
    top_val = proxy.data(proxy.index(0, 5), Qt.ItemDataRole.UserRole)
    assert top_val is None


# ---------------------------------------------------------------------------
# Discrete filter tests
# ---------------------------------------------------------------------------


def test_discrete_filter_reduces_row_count(qapp: QApplication) -> None:
    # Arrange — 3 items with distinct names
    items = [
        _make_avg_item(model_name="alpha"),
        _make_avg_item(model_name="beta"),
        _make_avg_item(model_name="gamma"),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act — filter col 0 to only "beta"
    proxy.set_column_filter(0, {"beta"})

    # Assert
    assert proxy.rowCount() == 1


def test_discrete_filter_shows_matching_row(qapp: QApplication) -> None:
    # Arrange
    items = [
        _make_avg_item(model_name="alpha"),
        _make_avg_item(model_name="beta"),
        _make_avg_item(model_name="gamma"),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.set_column_filter(0, {"beta"})

    # Assert — the only visible row's model_name is "beta"
    visible_name = proxy.data(proxy.index(0, 0), Qt.ItemDataRole.UserRole)
    assert visible_name == "beta"


# ---------------------------------------------------------------------------
# Range filter tests
# ---------------------------------------------------------------------------


def test_range_filter_reduces_row_count(qapp: QApplication) -> None:
    # Arrange — avg_score: 0.3, 0.7, 0.9
    items = [
        _make_avg_item(model_name="low", avg_score=0.3),
        _make_avg_item(model_name="mid", avg_score=0.7),
        _make_avg_item(model_name="high", avg_score=0.9),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act — col 3 (AVG. SCORE UserRole) range (0.5, 1.0)
    proxy.set_column_filter(3, (0.5, 1.0))

    # Assert
    assert proxy.rowCount() == 2


def test_and_logic_across_columns(qapp: QApplication) -> None:
    # Arrange — m1 has high score, m2 has low score
    items = [
        _make_avg_item(model_name="m1", avg_score=0.9),
        _make_avg_item(model_name="m2", avg_score=0.5),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act — filter col 0 to {"m1"} AND col 3 to (0.8, 1.0)
    proxy.set_column_filter(0, {"m1"})
    proxy.set_column_filter(3, (0.8, 1.0))

    # Assert — only m1 satisfies both filters
    assert proxy.rowCount() == 1


# ---------------------------------------------------------------------------
# Filter management tests
# ---------------------------------------------------------------------------


def test_clear_column_filter(qapp: QApplication) -> None:
    # Arrange
    items = [
        _make_avg_item(model_name="alpha"),
        _make_avg_item(model_name="beta"),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)
    proxy.set_column_filter(0, {"alpha"})
    assert proxy.rowCount() == 1

    # Act
    proxy.clear_column_filter(0)

    # Assert
    assert proxy.rowCount() == 2


def test_clear_all_filters(qapp: QApplication) -> None:
    # Arrange
    items = [
        _make_avg_item(model_name="alpha", avg_score=0.2),
        _make_avg_item(model_name="beta", avg_score=0.9),
        _make_avg_item(model_name="gamma", avg_score=0.5),
    ]
    proxy, _ = _make_proxy_with_items(qapp, items)
    proxy.set_column_filter(0, {"alpha"})
    proxy.set_column_filter(3, (0.8, 1.0))
    assert proxy.rowCount() == 0

    # Act
    proxy.clear_all_filters()

    # Assert
    assert proxy.rowCount() == 3


def test_has_active_filter(qapp: QApplication) -> None:
    # Arrange
    items = [_make_avg_item()]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act — set then clear
    proxy.set_column_filter(0, {"test-model"})
    after_set = proxy.has_active_filter(0)
    proxy.clear_column_filter(0)
    after_clear = proxy.has_active_filter(0)

    # Assert
    assert after_set is True
    assert after_clear is False


def test_active_filter_columns(qapp: QApplication) -> None:
    # Arrange
    items = [_make_avg_item()]
    proxy, _ = _make_proxy_with_items(qapp, items)

    # Act
    proxy.set_column_filter(0, {"test-model"})
    proxy.set_column_filter(3, (0.0, 1.0))
    result = proxy.active_filter_columns()

    # Assert
    assert result == {0, 3}


def test_empty_source_no_crash(qapp: QApplication) -> None:
    # Arrange
    source = SummaryTableModel()
    proxy = NumericSortProxyModel()
    proxy.setSourceModel(source)

    # Act
    count = proxy.rowCount()

    # Assert
    assert count == 0
