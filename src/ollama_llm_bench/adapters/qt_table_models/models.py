"""Row shapes rendered by ``adapters/qt_table_models``'s three table-model factories
(``01_MODULE_INVENTORY.md`` §5).

These structs are owned by this module, not by ``ui/results`` or ``ui/settings_dialog`` —
``adapters/*`` may depend only on ``backend/domain`` and PySide6, never on a ``ui/*``
view-model. A later UI-phase controller story maps its own richer view-model rows
(``SummaryViewModel``, ``DetailRowViewModel``, ``ProviderRow``) into these before calling
a model's ``set_rows``.
"""

import msgspec

from ollama_llm_bench.backend.domain import (
    NonEmptyStr,
    ProviderIdStr,
    ProviderTestStatus,
    ProviderType,
    ResultId,
)

__all__: list[str] = ["DetailsTableRow", "ProviderTableRow", "SummaryTableRow"]


class SummaryTableRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One summary-table row: one cell per mode-offered, visible column, in column order."""

    cells: tuple[str, ...]


class DetailsTableRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One details-table row: its identity plus one cell per visible column.

    ``result_id`` is not itself a rendered column — it is carried so a future
    controller can resolve a selected view row back to its ``BenchmarkResult``.
    """

    result_id: ResultId
    cells: tuple[str, ...]


class ProviderTableRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One providers-table row, covering the 6 data-bearing columns of
    ``06_Settings_Dialog/description.md`` §3.2 (Health, Name, Type, Base URL, Auth,
    Enabled). The spec's 7th column, Actions, has no data field — it is a later
    settings_dialog UI story's view/delegate concern, not this row's.
    """

    provider_id: ProviderIdStr
    label: NonEmptyStr
    provider_type: ProviderType
    base_url_display: str
    auth_badge: str
    health: ProviderTestStatus
    enabled: bool
