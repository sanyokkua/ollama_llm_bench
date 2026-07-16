"""The Details tab's table model (``05_Result_Widget/implementation_structure.md`` §6)."""

from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel
from ollama_llm_bench.adapters.qt_table_models.models import DetailsTableRow


def _cell_value(row: DetailsTableRow, column: int) -> str:
    return row.cells[column]


class _DetailsTableModel(_FrozenRowTableModel[DetailsTableRow]):
    """Renders ``DetailsTableRow`` collections; columns are mode-dependent and
    supplied by the caller at construction/``set_rows`` time. Each row also
    carries its ``result_id`` (see ``base.py``'s ``rows`` property) for a
    later controller to resolve a selected view row's identity."""

    def __init__(self, *, headers: tuple[str, ...], rows: tuple[DetailsTableRow, ...]) -> None:
        super().__init__(headers=headers, cell_value=_cell_value, rows=rows)
