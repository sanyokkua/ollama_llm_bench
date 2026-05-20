"""ProviderTableModel — table model for the providers settings tab."""

from __future__ import annotations

import dataclasses
from typing import Any, Final, override

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from ollama_llm_bench.backend.core.models import ProviderConfig
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult

COL_HEALTH: Final[int] = 0
COL_LABEL: Final[int] = 1
COL_TYPE: Final[int] = 2
COL_BASE_URL: Final[int] = 3
COL_ENABLED: Final[int] = 4
COL_ACTIONS: Final[int] = 5

_COLUMN_COUNT: Final[int] = 6
_HEADERS: Final[tuple[str, ...]] = ("", "Label", "Type", "Base URL", "Enabled", "")

_HEADER_TOOLTIPS: Final[tuple[str, ...]] = (
    "Connection health: green = reachable, orange = no models, red = down, blue = testing",
    "Provider label as shown in the run configuration",
    "Provider type: openai_compatible, anthropic, or gemini",
    "Base URL for the provider API endpoint",
    "Whether this provider is active and usable in benchmark runs",
    "",  # Actions column — no tooltip needed
)

_HEALTH_UNKNOWN: Final[str] = "unknown"
_HEALTH_LIVE: Final[str] = "live"
_HEALTH_WARNING: Final[str] = "warning"
_HEALTH_DOWN: Final[str] = "down"
_HEALTH_TESTING: Final[str] = "testing"

_HEALTH_COLORS: Final[dict[str, str]] = {
    _HEALTH_LIVE: "#4caf50",
    _HEALTH_WARNING: "#ff9800",
    _HEALTH_DOWN: "#f44336",
    _HEALTH_TESTING: "#2196f3",
    _HEALTH_UNKNOWN: "#9e9e9e",
}

_INVALID_INDEX: Final[QModelIndex] = QModelIndex()


@dataclasses.dataclass(slots=True)  # mutable by design: health state mutates in place
class _ProviderRowData:
    config: ProviderConfig
    health_state: str = _HEALTH_UNKNOWN
    health_tooltip: str = ""
    last_health: HealthCheckResult | None = None


class ProviderTableModel(QAbstractTableModel):
    """Table model backing the providers QTableView.

    Each row represents one provider. Health state and enable flag are updated
    in place without rebuilding the model; views receive targeted dataChanged signals.

    Signals:
        provider_user_edited: Emitted with the provider_id when the user directly
            toggles the Enabled checkbox. Programmatic set_enable() does NOT emit this.
    """

    provider_user_edited: Signal = Signal(str)

    def __init__(
        self,
        configs: list[ProviderConfig],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows: list[_ProviderRowData] = [_ProviderRowData(config=c) for c in configs]

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        if parent.isValid():
            return 0
        return _COLUMN_COUNT

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and 0 <= section < _COLUMN_COUNT:
            if role == Qt.ItemDataRole.DisplayRole:
                return _HEADERS[section]
            if role == Qt.ItemDataRole.ToolTipRole and section < len(_HEADER_TOOLTIPS) and _HEADER_TOOLTIPS[section]:
                return _HEADER_TOOLTIPS[section]
        return None

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._rows):
            return None
        row_data = self._rows[row]
        config = row_data.config

        match col:
            case _ if col == COL_HEALTH:
                if role == Qt.ItemDataRole.DisplayRole:
                    return "●"
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QColor(_HEALTH_COLORS.get(row_data.health_state, _HEALTH_COLORS[_HEALTH_UNKNOWN]))
                if role == Qt.ItemDataRole.ToolTipRole:
                    return row_data.health_tooltip or None
                if role == Qt.ItemDataRole.UserRole:
                    return row_data.health_state
                return None

            case _ if col == COL_LABEL:
                if role == Qt.ItemDataRole.DisplayRole:
                    return config.label
                if role == Qt.ItemDataRole.UserRole:
                    return config.provider_id
                return None

            case _ if col == COL_TYPE:
                if role == Qt.ItemDataRole.DisplayRole:
                    return config.provider_type.value
                return None

            case _ if col == COL_BASE_URL:
                if role == Qt.ItemDataRole.DisplayRole:
                    return config.base_url or ""
                return None

            case _ if col == COL_ENABLED:
                if role == Qt.ItemDataRole.CheckStateRole:
                    return Qt.CheckState.Checked if config.enabled else Qt.CheckState.Unchecked
                return None

            case _:
                # COL_ACTIONS — delegate handles rendering
                return None

    @override
    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid():
            return False
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._rows):
            return False
        if col == COL_ENABLED and role == Qt.ItemDataRole.CheckStateRole:
            enabled = value == Qt.CheckState.Checked
            row_data = self._rows[row]
            row_data.config = dataclasses.replace(row_data.config, enabled=enabled)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            self.provider_user_edited.emit(row_data.config.provider_id)
            return True
        return False

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        col = index.column()
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if col == COL_ENABLED:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if col == COL_ACTIONS:
            return Qt.ItemFlag.ItemIsEnabled
        return base

    # -------------------------------------------------------------------------
    # Read API
    # -------------------------------------------------------------------------

    def find_row(self, provider_id: str) -> int:
        """Return row index for provider_id, or -1 if not found."""
        for i, row_data in enumerate(self._rows):
            if row_data.config.provider_id == provider_id:
                return i
        return -1

    def get_config(self, row: int) -> ProviderConfig:
        """Return the current config for the given row."""
        return self._rows[row].config

    def all_configs(self) -> list[ProviderConfig]:
        """Return all configs in current order."""
        return [r.config for r in self._rows]

    def is_enabled(self, provider_id: str) -> bool:
        """Return True if the provider is currently enabled."""
        row = self.find_row(provider_id)
        return self._rows[row].config.enabled if row >= 0 else False

    def get_health_state(self, provider_id: str) -> str:
        """Return health state string: "live", "warning", "down", "testing", or "unknown"."""
        row = self.find_row(provider_id)
        return self._rows[row].health_state if row >= 0 else _HEALTH_UNKNOWN

    def get_health_result(self, provider_id: str) -> HealthCheckResult | None:
        """Return the last HealthCheckResult for this provider, or None."""
        row = self.find_row(provider_id)
        return self._rows[row].last_health if row >= 0 else None

    # -------------------------------------------------------------------------
    # Write API
    # -------------------------------------------------------------------------

    def update_config(self, row: int, config: ProviderConfig) -> None:
        """Replace config at row; emit dataChanged for the full row."""
        if row < 0 or row >= len(self._rows):
            return
        self._rows[row].config = config
        top_left = self.index(row, 0)
        bottom_right = self.index(row, _COLUMN_COUNT - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def append_config(self, config: ProviderConfig) -> int:
        """Append a new row; return its row index."""
        row = len(self._rows)
        self.beginInsertRows(_INVALID_INDEX, row, row)
        self._rows.append(_ProviderRowData(config=config))
        self.endInsertRows()
        return row

    def remove_row_for_provider(self, provider_id: str) -> None:
        """Remove the row whose provider_id matches; no-op if not found."""
        row = self.find_row(provider_id)
        if row == -1:
            return
        self.beginRemoveRows(_INVALID_INDEX, row, row)
        self._rows.pop(row)
        self.endRemoveRows()

    def set_enable(self, provider_id: str, enabled: bool) -> None:
        """Programmatically set the Enabled flag; does NOT emit provider_user_edited."""
        row = self.find_row(provider_id)
        if row == -1:
            return
        row_data = self._rows[row]
        row_data.config = dataclasses.replace(row_data.config, enabled=enabled)
        idx = self.index(row, COL_ENABLED)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.CheckStateRole])

    def set_health(self, provider_id: str, state: str, tooltip: str) -> None:
        """Set health state and tooltip directly (for disabled / env-var-missing cases)."""
        row = self.find_row(provider_id)
        if row == -1:
            return
        row_data = self._rows[row]
        row_data.health_state = state
        row_data.health_tooltip = tooltip
        idx = self.index(row, COL_HEALTH)
        self.dataChanged.emit(idx, idx)

    def apply_health_result(self, result: HealthCheckResult) -> None:
        """Compute health state from a HealthCheckResult and update the affected row."""
        if result.is_healthy and result.model_count > 0:
            state = _HEALTH_LIVE
            tooltip = f"{result.model_count} models available · {result.latency_ms} ms"
        elif result.is_healthy:
            state = _HEALTH_WARNING
            tooltip = f"Server reachable but no models found · {result.latency_ms} ms"
        else:
            state = _HEALTH_DOWN
            tooltip = result.error_message or "Provider unreachable."
        row = self.find_row(result.provider_id)
        if row == -1:
            return
        row_data = self._rows[row]
        row_data.health_state = state
        row_data.health_tooltip = tooltip
        row_data.last_health = result
        idx = self.index(row, COL_HEALTH)
        self.dataChanged.emit(idx, idx)
