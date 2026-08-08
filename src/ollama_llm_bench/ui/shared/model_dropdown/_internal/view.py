"""ModelDropdownWidget: QComboBox listing one provider's models (08-E §10)."""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QComboBox

from ollama_llm_bench.backend.domain import ModelName, ProviderId
from ollama_llm_bench.ui.shared.model_dropdown.protocols import ModelFetcher

type ModelFilter = Callable[[ModelName], bool]


class ModelDropdownWidget(QComboBox):
    """A combo over one provider's model list; refetches on `set_provider`."""

    model_changed = Signal(str)

    def __init__(
        self, *, model_fetcher: ModelFetcher, model_filter: ModelFilter | None = None
    ) -> None:
        """Build the (initially empty) combo.

        Args:
            model_fetcher: Off-GUI-thread model-list access for the selected provider.
            model_filter: When given, only models for which it returns `True` appear.
        """
        super().__init__()
        self._model_fetcher = model_fetcher
        self._model_filter = model_filter
        self._current_provider_id: ProviderId | None = None
        self.setProperty("role", "dropdown")
        self.setAccessibleName("Model")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.currentIndexChanged.connect(self._on_current_index_changed)

    def set_provider(self, provider_id: ProviderId) -> None:
        """Refetch and repopulate this combo from `provider_id`'s model list."""
        self._current_provider_id = provider_id
        with QSignalBlocker(self):
            self.clear()
        self._model_fetcher.fetch_models(
            provider_id, on_success=self._on_models_fetched, on_error=self._on_fetch_failed
        )

    def _on_models_fetched(self, provider_id: ProviderId, models: tuple[ModelName, ...]) -> None:
        if provider_id != self._current_provider_id:
            return  # stale result from a superseded fetch
        visible = tuple(
            model for model in models if self._model_filter is None or self._model_filter(model)
        )
        with QSignalBlocker(self):
            self.clear()
            for model in visible:
                self.addItem(model, model)
            self.setCurrentIndex(0 if self.count() else -1)

    def _on_fetch_failed(self, provider_id: ProviderId, _error: Exception) -> None:
        if provider_id != self._current_provider_id:
            return  # stale result from a superseded fetch
        with QSignalBlocker(self):
            self.clear()

    def _on_current_index_changed(self, index: int) -> None:
        model_name = self.itemData(index) if index >= 0 else None
        if isinstance(model_name, str):
            self.model_changed.emit(model_name)
