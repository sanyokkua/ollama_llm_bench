"""TestModelsWidget — cross-provider test model selection widget."""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtCore import QObject, QRunnable, QSignalBlocker, Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import ModelDescriptor, ModelSelectionKey
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.control.test_models_selection_store import (
    TestModelsSelectionStore,
)
from ollama_llm_bench.ui.widgets.panels.control.test_models_summary_widget import (
    TestModelsSummaryWidget,
)

_logger = logging.getLogger(__name__)

_PLACEHOLDER_TEXT: Final[str] = "No providers available — open Settings to enable one"
_BROWSE_COMBO_TOOLTIP: Final[str] = (
    "Switch provider to browse its available models. This never clears selections from other providers."
)
_CLEAR_SELECTION_TOOLTIP: Final[str] = "Remove every selected model across all providers."
_REMOVED_LABEL_TEXT: Final[str] = "Some previously selected models are no longer available and were removed."


class _ModelFetchWorker(QRunnable):
    """Background worker that fetches model names for a given provider.

    Runs on QThreadPool. Emits ``finished`` with the model name list on the
    main thread via Qt's cross-thread signal delivery.
    """

    class Signals(QObject):
        """Typed signals for _ModelFetchWorker."""

        finished: Signal = Signal(str, list)  # provider_id, list[ModelDescriptor]

    def __init__(self, provider_id: str, controller: RunConfigController) -> None:
        """Initialise the fetch worker.

        Args:
            provider_id: The provider whose models will be fetched.
            controller: Controller used to query available models.
        """
        super().__init__()
        self.signals = _ModelFetchWorker.Signals()
        self._provider_id = provider_id
        self._controller = controller
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        """Fetch models from the provider and emit the result.

        Never raises — errors are logged and an empty list is emitted.
        """
        try:
            descriptors = self._controller.get_descriptors_for_provider(self._provider_id)
        except Exception:
            _logger.warning(
                "Failed to fetch models for provider %s",
                self._provider_id,
                exc_info=True,
            )
            descriptors = []
        self.signals.finished.emit(self._provider_id, descriptors)


class TestModelsWidget(QWidget):
    """Cross-provider test model selection widget.

    Implements multi-provider persistent selection: browsing a different provider
    in the combo box only changes which models are shown in the available list;
    it never clears selections already made for other providers.

    The :class:`TestModelsSelectionStore` owned by this widget is the single
    source of truth. Check states in the available list are always derived from
    the store, never the inverse.

    Layout (top to bottom)::

        QGroupBox("Test Models")
          QLabel("Provider")
          QHBoxLayout:
            QComboBox(_browse_combo)     ← enabled providers, browse filter only
            QPushButton("Refresh")       ← re-fetches available models
          QLabel("Available Models")
          QListWidget(_available_list)   ← ItemIsUserCheckable items
          QHBoxLayout:
            QPushButton("Select All")    ← scoped to browsed provider
            QPushButton("Clear All")     ← scoped to browsed provider
          TestModelsSummaryWidget(_summary)
          QPushButton("Clear Selection") ← global clear
          QLabel(_removed_label)         ← shown when models disappear on refresh
    """

    def __init__(
        self,
        *,
        controller: RunConfigController,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the widget.

        Args:
            controller: Provides provider/model discovery and embedding-filter
                queries; must already be wired to the application context.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._controller = controller
        self._threadpool = QThreadPool.globalInstance()
        self._store = TestModelsSelectionStore(self)
        self._last_browse_provider_id: str = ""
        # Cache of fetched models per provider: provider_id → list[str]
        self._provider_models: dict[str, list[str]] = {}
        # Cache of full descriptors per provider: provider_id → model_name → ModelDescriptor
        self._provider_descriptors: dict[str, dict[str, ModelDescriptor]] = {}

        self._create_widgets()
        self._configure_widgets()
        self._build_layout()
        self._connect_signals()
        self._refresh_providers()
        self._controller.subscribe_to_provider_registry_reloaded(self._refresh_providers, parent=self)

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        from PySide6.QtWidgets import QComboBox

        self._provider_label = QLabel("Provider")
        self._browse_combo = QComboBox()
        self._refresh_btn = QPushButton("Refresh")
        self._available_label = QLabel("Available Models")
        self._available_list = QListWidget()
        self._select_all_btn = QPushButton("Select All")
        self._clear_all_btn = QPushButton("Clear All")
        self._summary = TestModelsSummaryWidget(store=self._store, parent=self)
        self._clear_selection_btn = QPushButton("Clear Selection")
        self._removed_label = QLabel(_REMOVED_LABEL_TEXT)

    # ------------------------------------------------------------------
    # Widget configuration
    # ------------------------------------------------------------------

    def _configure_widgets(self) -> None:
        self._provider_label.setProperty("role", "secondary")
        self._available_label.setProperty("role", "secondary")

        self._browse_combo.setToolTip(_BROWSE_COMBO_TOOLTIP)

        self._available_list.setToolTip(
            "Available models from the selected provider."
            " Double-click or use the Add button to include a model in the benchmark run."
        )

        self._refresh_btn.setProperty("size", "small")
        self._refresh_btn.setToolTip("Re-fetch the available models for the selected provider.")

        self._select_all_btn.setProperty("size", "small")
        self._clear_all_btn.setProperty("size", "small")
        self._clear_selection_btn.setProperty("size", "small")
        self._clear_selection_btn.setToolTip(_CLEAR_SELECTION_TOOLTIP)

        self._removed_label.setWordWrap(True)
        self._removed_label.setProperty("role", "secondary")
        self._removed_label.setVisible(False)

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        provider_row = QHBoxLayout()
        provider_row.setContentsMargins(0, 0, 0, 0)
        provider_row.setSpacing(4)
        provider_row.addWidget(self._browse_combo, stretch=1)
        provider_row.addWidget(self._refresh_btn)

        scope_btn_row = QHBoxLayout()
        scope_btn_row.setContentsMargins(0, 0, 0, 0)
        scope_btn_row.setSpacing(4)
        scope_btn_row.addWidget(self._select_all_btn)
        scope_btn_row.addWidget(self._clear_all_btn)
        scope_btn_row.addStretch()

        inner = QVBoxLayout()
        inner.setContentsMargins(4, 4, 4, 4)
        inner.setSpacing(3)
        inner.addWidget(self._provider_label)
        inner.addLayout(provider_row)
        inner.addWidget(self._available_label)
        inner.addWidget(self._available_list)
        inner.addLayout(scope_btn_row)
        inner.addWidget(self._summary)
        inner.addWidget(self._clear_selection_btn)
        inner.addWidget(self._removed_label)

        group = QGroupBox("Test Models")
        group.setLayout(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(group)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._browse_combo.currentIndexChanged.connect(self._on_browse_provider_changed)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._available_list.itemChanged.connect(self._on_item_changed)
        self._select_all_btn.clicked.connect(self._on_select_all_clicked)
        self._clear_all_btn.clicked.connect(self._on_clear_all_clicked)
        self._clear_selection_btn.clicked.connect(self._store.clear_all)

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def _refresh_providers(self) -> None:
        """Repopulate the browse combo with currently enabled providers."""
        current = self._browse_combo.currentText()
        providers = self._controller.get_provider_names()

        blocker = QSignalBlocker(self._browse_combo)
        self._browse_combo.clear()

        if not providers:
            self._browse_combo.addItem(_PLACEHOLDER_TEXT)
            del blocker
            self._available_list.clear()
            return

        for provider_id in providers:
            self._browse_combo.addItem(provider_id)

        del blocker

        # Restore previous selection if still available
        if current and current in providers:
            idx = self._browse_combo.findText(current)
            if idx >= 0:
                self._browse_combo.setCurrentIndex(idx)
                if self._browse_combo.currentIndex() == idx:
                    self._fetch_models(current)
                return

        self._browse_combo.setCurrentIndex(0)
        first = self._browse_combo.currentText()
        if first and first != _PLACEHOLDER_TEXT:
            self._fetch_models(first)

    # ------------------------------------------------------------------
    # Model fetching (background)
    # ------------------------------------------------------------------

    def _fetch_models(self, provider_id: str) -> None:
        """Start a background fetch of models for ``provider_id``."""
        if not provider_id or provider_id == _PLACEHOLDER_TEXT:
            return
        worker = _ModelFetchWorker(provider_id, self._controller)
        worker.signals.finished.connect(self._on_models_fetched)
        self._threadpool.start(worker)

    @Slot(str, list)
    def _on_models_fetched(self, provider_id: str, descriptors: list[ModelDescriptor]) -> None:
        """Handle freshly fetched model list on the main thread.

        Caches the result, then populates the available list if the browsed
        provider matches. Also prunes from the store any selections that are
        no longer present in the fetched list.

        Args:
            provider_id: The provider the fetch was initiated for.
            descriptors: Full ModelDescriptor list returned by the provider.
        """
        model_names = [d.model_name for d in descriptors]
        # Detect removed selections
        removed_count = self._prune_missing_models(provider_id, model_names)
        self._provider_models[provider_id] = model_names
        self._provider_descriptors[provider_id] = {d.model_name: d for d in descriptors}
        self._removed_label.setVisible(removed_count > 0)

        # Only repopulate if this provider is still browsed
        if self._browse_combo.currentText() == provider_id:
            self._populate_available_list(provider_id, model_names)

    def _prune_missing_models(self, provider_id: str, available_models: list[str]) -> int:
        """Remove from the store any selections for ``provider_id`` that are no longer available.

        Args:
            provider_id: The provider whose models have been refreshed.
            available_models: The new set of available model names.

        Returns:
            The number of models that were removed from the store.
        """
        available_set = set(available_models)
        selected_for_provider = self._store.filter_by_provider(provider_id)
        removed = 0
        for descriptor in selected_for_provider:
            if descriptor.model_name not in available_set:
                key = ModelSelectionKey(provider_id=provider_id, model_name=descriptor.model_name)
                self._store.remove(key)
                removed += 1
        if removed:
            _logger.info(
                "Pruned %d unavailable model(s) for provider %s",
                removed,
                provider_id,
            )
        return removed

    # ------------------------------------------------------------------
    # Available list population
    # ------------------------------------------------------------------

    def _populate_available_list(self, provider_id: str, models: list[str]) -> None:
        """Repopulate the available list for the given provider.

        Preserves the vertical scroll position when the same provider is
        browsed again; resets to top when switching providers.
        Applies the embedding filter if enabled.

        Args:
            provider_id: The provider whose models are being shown.
            models: Full model name list from the provider.
        """
        scroll_bar = self._available_list.verticalScrollBar()
        scroll_pos = scroll_bar.value() if scroll_bar is not None else 0

        blocker = QSignalBlocker(self._available_list)
        self._available_list.clear()

        filter_enabled = self._controller.is_embedding_filter_enabled()
        for name in models:
            if filter_enabled and self._controller.is_embedding_model(name):
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            key = ModelSelectionKey(provider_id=provider_id, model_name=name)
            item.setCheckState(Qt.CheckState.Checked if self._store.contains(key) else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._available_list.addItem(item)

        del blocker  # QSignalBlocker released here

        if provider_id == self._last_browse_provider_id and scroll_bar is not None:
            scroll_bar.setValue(scroll_pos)
        self._last_browse_provider_id = provider_id

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_browse_provider_changed(self, _index: int) -> None:
        """React to the user selecting a different provider in the browse combo.

        Repopulates the available list from the cache (or fetches if not cached).
        Updates Select All / Clear All tooltip text.

        Args:
            _index: Combo box index (unused — provider text is read directly).
        """
        provider_id = self._browse_combo.currentText()
        if not provider_id or provider_id == _PLACEHOLDER_TEXT:
            blocker = QSignalBlocker(self._available_list)
            self._available_list.clear()
            del blocker
            return

        self._update_scope_button_tooltips(provider_id)
        self._removed_label.setVisible(False)

        if provider_id in self._provider_models:
            self._populate_available_list(provider_id, self._provider_models[provider_id])
        else:
            self._fetch_models(provider_id)

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Re-fetch models for the currently browsed provider."""
        provider_id = self._browse_combo.currentText()
        if provider_id and provider_id != _PLACEHOLDER_TEXT:
            self._fetch_models(provider_id)

    @Slot(QListWidgetItem)
    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Synchronise a check-state change in the available list with the store.

        Args:
            item: The list widget item whose check state changed.
        """
        key: ModelSelectionKey = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            provider_label = self._browse_combo.currentText()
            descriptor = self._provider_descriptors.get(key.provider_id, {}).get(key.model_name)
            if descriptor is None:
                descriptor = ModelDescriptor(
                    provider_id=key.provider_id,
                    provider_type="",
                    model_name=key.model_name,
                    display_label=f"{provider_label} · {key.model_name}",
                )
            self._store.add(descriptor)
        else:
            self._store.remove(key)

    @Slot()
    def _on_select_all_clicked(self) -> None:
        """Select all visible models in the available list (scoped to browsed provider)."""
        blocker = QSignalBlocker(self._available_list)
        for i in range(self._available_list.count()):
            item = self._available_list.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)
        del blocker
        # Sync store after bulk change
        self._sync_all_items_to_store()

    @Slot()
    def _on_clear_all_clicked(self) -> None:
        """Uncheck all visible models in the available list (scoped to browsed provider)."""
        blocker = QSignalBlocker(self._available_list)
        for i in range(self._available_list.count()):
            item = self._available_list.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)
        del blocker
        # Sync store after bulk change
        self._sync_all_items_to_store()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sync_all_items_to_store(self) -> None:
        """Walk all visible items and reconcile their check states with the store.

        Called after bulk Select All / Clear All operations to avoid per-item
        ``itemChanged`` emissions during the signal-blocked loop.
        """
        provider_label = self._browse_combo.currentText()
        for i in range(self._available_list.count()):
            item = self._available_list.item(i)
            if item is None:
                continue
            key: ModelSelectionKey = item.data(Qt.ItemDataRole.UserRole)
            if item.checkState() == Qt.CheckState.Checked:
                if not self._store.contains(key):
                    descriptor = self._provider_descriptors.get(key.provider_id, {}).get(key.model_name)
                    if descriptor is None:
                        descriptor = ModelDescriptor(
                            provider_id=key.provider_id,
                            provider_type="",
                            model_name=key.model_name,
                            display_label=f"{provider_label} · {key.model_name}",
                        )
                    self._store.add(descriptor)
            else:
                if self._store.contains(key):
                    self._store.remove(key)

    def _update_scope_button_tooltips(self, provider_label: str) -> None:
        """Update Select All and Clear All tooltips to reflect the current provider.

        Args:
            provider_label: Display name of the provider currently shown in the combo.
        """
        self._select_all_btn.setToolTip(
            f"Select all models from {provider_label}. Selections in other providers are unaffected."  # noqa: S608
        )
        self._clear_all_btn.setToolTip(
            f"Clear all models from {provider_label}. Selections in other providers are unaffected."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selection_store(self) -> TestModelsSelectionStore:
        """Return the selection store owned by this widget.

        Returns:
            The :class:`TestModelsSelectionStore` holding all cross-provider
            model selections.
        """
        return self._store
