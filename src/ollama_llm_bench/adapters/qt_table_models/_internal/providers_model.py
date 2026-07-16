"""The Providers tab's table model (``06_Settings_Dialog/description.md`` §3.2:
Health, Name, Type, Base URL, Auth, Enabled — the 7th spec column, Actions, has no
data field and is a later settings_dialog UI story's view/delegate concern)."""

from collections.abc import Callable

from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel
from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow

_HEADERS: tuple[str, ...] = ("Health", "Name", "Type", "Base URL", "Auth", "Enabled")

_COLUMN_GETTERS: tuple[Callable[[ProviderTableRow], str], ...] = (
    lambda row: row.health.value,
    lambda row: row.label,
    lambda row: row.provider_type.value,
    lambda row: row.base_url_display,
    lambda row: row.auth_badge,
    lambda row: str(row.enabled),
)


def _cell_value(row: ProviderTableRow, column: int) -> str:
    return _COLUMN_GETTERS[column](row)


class _ProvidersTableModel(_FrozenRowTableModel[ProviderTableRow]):
    """Renders ``ProviderTableRow`` collections over the fixed 6-column header set."""

    def __init__(self, *, rows: tuple[ProviderTableRow, ...]) -> None:
        super().__init__(headers=_HEADERS, cell_value=_cell_value, rows=rows)
