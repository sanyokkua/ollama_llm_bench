"""JudgeWidget — provider and model selector for the judge configuration section."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QSignalBlocker, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController

_logger = logging.getLogger(__name__)

_PLACEHOLDER_TEXT = "No providers available — open Settings to enable one"
_FILTER_WARNING_TEXT = "Embedding models hidden. Disable the filter in Settings → General if needed."
_PROVIDER_TOOLTIP = "Only enabled providers are listed. Enable providers in Settings → Providers."
_MODEL_TOOLTIP = "Models available from the selected judge provider."
_REFRESH_TOOLTIP = "Re-fetch the list of available providers and models."


class _ModelFetchWorker(QRunnable):
    """Background worker that fetches model names for a given provider.

    Runs on QThreadPool. Emits ``finished`` with the model name list on the
    main thread via Qt's cross-thread signal delivery.
    """

    class Signals(QObject):
        """Typed signals for _ModelFetchWorker."""

        finished: Signal = Signal(list)  # list[str]

    def __init__(self, provider_id: str, controller: RunConfigController) -> None:
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
            models = self._controller.get_models_for_provider(self._provider_id)
        except Exception:
            _logger.warning(
                "Failed to fetch models for provider %s",
                self._provider_id,
                exc_info=True,
            )
            models = []
        self.signals.finished.emit(models)


class JudgeWidget(QWidget):
    """Judge provider and model selector.

    Displays only enabled providers in the provider combo. Fetches models
    for the selected provider on a background thread. Optionally filters
    embedding models based on the controller's current setting.

    Layout::

        QLabel("Judge Provider")
        QHBoxLayout:
            QComboBox(_provider_combo)
            QPushButton("Refresh")
        QLabel("Judge Model")
        QComboBox(_model_combo)
        QLabel(_filter_warning_label)   ← shown only when models were filtered
    """

    def __init__(
        self,
        *,
        controller: RunConfigController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._threadpool = QThreadPool.globalInstance()

        self._create_widgets()
        self._configure_widgets()
        self._build_layout()
        self._connect_signals()
        self._refresh_providers()
        self._controller.subscribe_to_provider_registry_reloaded(self._refresh_providers)

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        self._provider_label = QLabel("Judge Provider")
        self._provider_combo = QComboBox()
        self._refresh_btn = QPushButton("Refresh")
        self._model_label = QLabel("Judge Model")
        self._model_combo = QComboBox()
        self._filter_warning_label = QLabel(_FILTER_WARNING_TEXT)

    def _configure_widgets(self) -> None:
        self._provider_combo.setToolTip(_PROVIDER_TOOLTIP)
        self._model_combo.setToolTip(_MODEL_TOOLTIP)
        self._refresh_btn.setToolTip(_REFRESH_TOOLTIP)
        self._refresh_btn.setProperty("size", "small")

        self._filter_warning_label.setWordWrap(True)
        self._filter_warning_label.setProperty("role", "secondary")
        self._filter_warning_label.setVisible(False)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        provider_row = QHBoxLayout()
        provider_row.setContentsMargins(0, 0, 0, 0)
        provider_row.setSpacing(4)
        provider_row.addWidget(self._provider_combo, stretch=1)
        provider_row.addWidget(self._refresh_btn)

        inner = QVBoxLayout()
        inner.setContentsMargins(4, 4, 4, 4)
        inner.setSpacing(3)
        inner.addWidget(self._provider_label)
        inner.addLayout(provider_row)
        inner.addWidget(self._model_label)
        inner.addWidget(self._model_combo)
        inner.addWidget(self._filter_warning_label)

        group = QGroupBox("Judge")
        group.setLayout(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(group)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._provider_combo.currentIndexChanged.connect(self._on_provider_index_changed)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def _refresh_providers(self) -> None:
        """Repopulate the provider combo with currently enabled providers.

        If no providers are available, inserts a non-selectable placeholder
        and disables the model combo. If the previously selected provider is
        no longer present, selects the first available item.
        """
        current_provider = self.get_selected_provider()

        providers = self._controller.get_healthy_provider_ids()

        blocker = QSignalBlocker(self._provider_combo)
        self._provider_combo.clear()

        if not providers:
            self._provider_combo.addItem(_PLACEHOLDER_TEXT)
            # Mark item non-selectable via QStandardItemModel
            std_model = self._provider_combo.model()
            if isinstance(std_model, QStandardItemModel):
                placeholder_item = std_model.item(0)
                if placeholder_item is not None:
                    placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._model_combo.setEnabled(False)
            self._model_combo.clear()
            self._filter_warning_label.setVisible(False)
            del blocker  # release before early return
            return

        self._model_combo.setEnabled(True)
        for provider_id in providers:
            self._provider_combo.addItem(provider_id)

        # Restore previous selection if still available
        del blocker  # release signal blocker before potentially triggering

        if current_provider and current_provider in providers:
            idx = self._provider_combo.findText(current_provider)
            if idx >= 0:
                self._provider_combo.setCurrentIndex(idx)
                # If index didn't change, currentIndexChanged won't fire; refresh manually.
                if self._provider_combo.currentIndex() == idx:
                    self._refresh_models(current_provider)
                return

        # Select first item — triggers currentIndexChanged → _refresh_models
        self._provider_combo.setCurrentIndex(0)
        first_provider = self._provider_combo.currentText()
        if (
            current_provider
            and current_provider not in providers
            and first_provider
            and first_provider != _PLACEHOLDER_TEXT
        ):
            self._controller.show_status_message(
                f"Judge provider '{current_provider}' is no longer available; selecting '{first_provider}'."
            )
        if first_provider:
            self._refresh_models(first_provider)

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def _refresh_models(self, provider_id: str) -> None:
        """Start a background fetch of models for ``provider_id``."""
        if not provider_id or provider_id == _PLACEHOLDER_TEXT:
            return

        worker = _ModelFetchWorker(provider_id, self._controller)
        worker.signals.finished.connect(self._on_models_fetched)
        self._threadpool.start(worker)

    @Slot(list)
    def _on_models_fetched(self, models: list[str]) -> None:
        """Populate the model combo on the main thread.

        Applies the embedding filter when enabled and shows or hides the
        warning label based on whether any models were excluded.

        Args:
            models: Raw list of model names returned by the provider.
        """
        filter_enabled = self._controller.is_embedding_filter_enabled()
        filtered: list[str] = []
        hidden_count = 0

        for name in models:
            if filter_enabled and self._controller.is_embedding_model(name):
                hidden_count += 1
            else:
                filtered.append(name)

        blocker = QSignalBlocker(self._model_combo)
        self._model_combo.clear()
        self._model_combo.addItems(filtered)
        del blocker

        self._filter_warning_label.setVisible(hidden_count > 0)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_provider_index_changed(self, _index: int) -> None:
        provider_id = self._provider_combo.currentText()
        self._refresh_models(provider_id)

    @Slot()
    def _on_refresh_clicked(self) -> None:
        self._refresh_providers()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_provider(self) -> str | None:
        """Return the currently selected provider ID.

        Returns:
            Provider ID string, or ``None`` if no real provider is selected
            (i.e., the placeholder is shown or the combo is empty).
        """
        text = self._provider_combo.currentText()
        if not text or text == _PLACEHOLDER_TEXT:
            return None
        return text

    def get_selected_model(self) -> str | None:
        """Return the currently selected model name.

        Returns:
            Model name string, or ``None`` if the model combo is empty.
        """
        text = self._model_combo.currentText()
        return text if text else None
