"""Public factories for the summary, details, and providers ``QAbstractTableModel``
adapters (``01_MODULE_INVENTORY.md`` §5). Each returned model reads only the frozen
row struct it is given, holds no backend Protocol, and performs no I/O."""

import icontract
from PySide6.QtCore import QAbstractTableModel

from ollama_llm_bench.adapters.qt_table_models._internal.details_model import _DetailsTableModel
from ollama_llm_bench.adapters.qt_table_models._internal.providers_model import (
    _ProvidersTableModel,
)
from ollama_llm_bench.adapters.qt_table_models._internal.summary_model import _SummaryTableModel
from ollama_llm_bench.adapters.qt_table_models.models import (
    DetailsTableRow,
    ProviderTableRow,
    SummaryTableRow,
)

__all__: list[str] = [
    "make_details_table_model",
    "make_providers_table_model",
    "make_summary_table_model",
]


@icontract.require(
    lambda headers, rows: all(len(row.cells) == len(headers) for row in rows),
    "every row's cell count must match the supplied header count — the caller "
    "(the Result widget's Summary controller) builds both from the same "
    "mode-offered column list and must never pass them out of step",
)
@icontract.ensure(lambda result: result is not None)
def make_summary_table_model(
    *,
    headers: tuple[str, ...],
    rows: tuple[SummaryTableRow, ...],
) -> QAbstractTableModel:
    """Construct the Summary tab's table model.

    Args:
        headers: The mode-offered, visible column labels, in display order.
        rows: One row per (provider, model) group, each already shaped to
            ``headers``.

    Returns:
        A ``QAbstractTableModel`` ready for a ``QTableView`` and reset via
        its ``set_rows`` when the Summary controller supplies new data.
    """
    return _SummaryTableModel(headers=headers, rows=rows)


@icontract.require(
    lambda headers, rows: all(len(row.cells) == len(headers) for row in rows),
    "every row's cell count must match the supplied header count — the caller "
    "(the Result widget's Details controller) builds both from the same "
    "mode-offered column list and must never pass them out of step",
)
@icontract.ensure(lambda result: result is not None)
def make_details_table_model(
    *,
    headers: tuple[str, ...],
    rows: tuple[DetailsTableRow, ...],
) -> QAbstractTableModel:
    """Construct the Details tab's table model.

    Args:
        headers: The mode-offered, visible column labels, in display order.
        rows: One row per ``BenchmarkResult``, each carrying its ``result_id``
            plus cells already shaped to ``headers``.

    Returns:
        A ``QAbstractTableModel`` ready for a ``QTableView`` and reset via
        its ``set_rows`` when the Details controller supplies new data.
    """
    return _DetailsTableModel(headers=headers, rows=rows)


@icontract.ensure(lambda result: result is not None)
def make_providers_table_model(
    *,
    rows: tuple[ProviderTableRow, ...],
) -> QAbstractTableModel:
    """Construct the Providers tab's table model.

    Args:
        rows: One row per ``ProviderConfig`` in ``provider_order``.

    Returns:
        A ``QAbstractTableModel`` over the fixed 6-column header set (Health,
        Name, Type, Base URL, Auth, Enabled), ready for a ``QTableView`` and
        reset via its ``set_rows`` when the Providers tab supplies new data.
    """
    return _ProvidersTableModel(rows=rows)
