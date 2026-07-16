"""The Summary tab's table model (``05_Result_Widget/implementation_structure.md`` §6)."""

from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel
from ollama_llm_bench.adapters.qt_table_models.models import SummaryTableRow


def _cell_value(row: SummaryTableRow, column: int) -> str:
    return row.cells[column]


class _SummaryTableModel(_FrozenRowTableModel[SummaryTableRow]):
    """Renders ``SummaryTableRow`` collections; columns are mode-dependent and
    supplied by the caller at construction/``set_rows`` time."""

    def __init__(self, *, headers: tuple[str, ...], rows: tuple[SummaryTableRow, ...]) -> None:
        super().__init__(headers=headers, cell_value=_cell_value, rows=rows)
