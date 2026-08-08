"""ProviderDropdownWidget: QComboBox listing enabled providers by name (08-E §9, 08-J §5.6)."""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QComboBox

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.events import SIGNAL_PROVIDER_REGISTRY_RELOADED, EventBus
from ollama_llm_bench.ui.shared.provider_dropdown.protocols import ProviderListSource

type ProviderFilter = Callable[[ProviderConfig], bool]


class ProviderDropdownWidget(QComboBox):
    """A combo over the enabled-provider catalog; rebuilds on registry reload."""

    provider_changed = Signal(str)

    def __init__(
        self,
        *,
        provider_source: ProviderListSource,
        event_bus: EventBus,
        provider_filter: ProviderFilter | None = None,
    ) -> None:
        """Build the combo, populate it once, and subscribe to registry reloads.

        Args:
            provider_source: Read-only access to the enabled-provider catalog.
            event_bus: The bus this widget rebuilds itself from on registry reload.
            provider_filter: When given, only providers for which it returns `True` appear.
        """
        super().__init__()
        self._provider_source = provider_source
        self._provider_filter = provider_filter
        self.setProperty("role", "dropdown")
        self.setAccessibleName("Provider")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._populate()
        self.currentIndexChanged.connect(self._on_current_index_changed)
        event_bus.subscribe(
            SIGNAL_PROVIDER_REGISTRY_RELOADED, self._on_registry_reloaded, owner=self
        )

    def _visible_providers(self) -> tuple[ProviderConfig, ...]:
        providers = self._provider_source.list_enabled()
        if self._provider_filter is None:
            return providers
        return tuple(provider for provider in providers if self._provider_filter(provider))

    def _populate(self) -> None:
        previous_id = self.currentData()
        previous_id = previous_id if isinstance(previous_id, str) else None
        with QSignalBlocker(self):
            self.clear()
            for provider in self._visible_providers():
                self.addItem(provider.name, provider.provider_id)
            restored_index = self.findData(previous_id) if previous_id is not None else -1
            self.setCurrentIndex(
                restored_index if restored_index >= 0 else (0 if self.count() else -1)
            )

    def _on_current_index_changed(self, index: int) -> None:
        provider_id = self.itemData(index) if index >= 0 else None
        if isinstance(provider_id, str):
            self.provider_changed.emit(provider_id)

    def _on_registry_reloaded(self, _event: object) -> None:
        self._populate()
