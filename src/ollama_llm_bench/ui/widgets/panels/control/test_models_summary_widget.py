"""Read-only summary widget showing every selected model across all providers."""

import functools
import logging

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import ModelDescriptor, ModelSelectionKey
from ollama_llm_bench.ui.widgets.panels.control.test_models_selection_store import (
    TestModelsSelectionStore,
)

logger = logging.getLogger(__name__)

_EMPTY_STATE_TEXT = "No models selected. Pick from the list above. You can mix models from multiple providers."
_REMOVE_TOOLTIP = "Remove this model from the selection"
_HEADER_EMPTY = "Selected models"


class TestModelsSummaryWidget(QWidget):
    """Read-only summary of all models currently selected across providers.

    Connects to ``TestModelsSelectionStore.selection_changed`` and rebuilds its
    row list on every change. Each row shows the provider prefix, the model name,
    and a remove button that removes the entry directly from the store.
    """

    def __init__(
        self,
        *,
        store: TestModelsSelectionStore,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the summary widget and connect to the store.

        Args:
            store: The shared selection store whose state this widget mirrors.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._store = store

        self._header_label = QLabel(_HEADER_EMPTY)
        self._header_label.setProperty("role", "secondary")

        self._empty_label = QLabel(_EMPTY_STATE_TEXT)
        self._empty_label.setWordWrap(True)
        self._empty_label.setProperty("role", "secondary")

        self._row_container = QWidget()
        self._row_layout = QVBoxLayout(self._row_container)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(4)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setWidget(self._row_container)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(8)
        outer_layout.addWidget(self._header_label)
        outer_layout.addWidget(self._empty_label)
        outer_layout.addWidget(self._scroll_area)

        store.selection_changed.connect(self._rebuild)
        self._rebuild()

    def _build_provider_prefix(self, descriptor: ModelDescriptor) -> str:
        """Return a short provider prefix derived from the descriptor's display label.

        Args:
            descriptor: The model descriptor whose label is used.

        Returns:
            The portion of ``display_label`` before the first `` · `` separator,
            or ``provider_id`` when no separator is present.
        """
        if " · " in descriptor.display_label:
            return descriptor.display_label.split(" · ")[0]
        return descriptor.provider_id

    def _build_row(self, key: ModelSelectionKey, descriptor: ModelDescriptor) -> QWidget:
        """Construct a single model row widget with a label and remove button.

        Args:
            key: The composite key used to remove the model from the store.
            descriptor: The model descriptor supplying display information.

        Returns:
            A QWidget containing the horizontal row layout.
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        prefix = self._build_provider_prefix(descriptor)
        label = QLabel(f"{prefix} · {descriptor.model_name}")
        label.setWordWrap(False)

        remove_button = QToolButton()
        remove_button.setText("×")  # noqa: RUF001  # Intentional multiplication sign for remove button label
        remove_button.setToolTip(_REMOVE_TOOLTIP)
        remove_button.clicked.connect(functools.partial(self._store.remove, key))

        row_layout.addWidget(label, stretch=1)
        row_layout.addWidget(remove_button)

        return row_widget

    def _rebuild(self) -> None:
        """Clear all existing rows and repopulate from the current store state."""
        while self._row_layout.count():
            item = self._row_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        descriptors: list[ModelDescriptor] = self._store.all()
        is_empty = len(descriptors) == 0

        if is_empty:
            self._header_label.setText(_HEADER_EMPTY)
        else:
            provider_count = len({d.provider_id for d in descriptors})
            self._header_label.setText(f"Selected models ({len(descriptors)} across {provider_count} providers)")

        for descriptor in descriptors:
            key = ModelSelectionKey(
                provider_id=descriptor.provider_id,
                model_name=descriptor.model_name,
            )
            row = self._build_row(key, descriptor)
            self._row_layout.addWidget(row)

        self._empty_label.setVisible(is_empty)
        self._scroll_area.setVisible(not is_empty)

        logger.debug(
            "summary_widget_rebuilt",
            extra={"model_count": len(descriptors)},
        )
