"""In-memory ordered store for cross-provider test model selections."""

import logging

from PySide6.QtCore import QObject, Signal

from ollama_llm_bench.backend.core.models import ModelDescriptor, ModelSelectionKey

logger = logging.getLogger(__name__)


class TestModelsSelectionStore(QObject):
    """Ordered dict-based store for cross-provider model selections.

    The store is the single source of truth for which (provider_id, model_name) pairs
    are selected for a benchmark run. Switching the provider browse combobox never clears
    this store — it only changes which provider's models are shown in the available list.
    """

    selection_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the store with an empty selection dict.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._items: dict[ModelSelectionKey, ModelDescriptor] = {}

    def add(self, descriptor: ModelDescriptor) -> None:
        """Add a model descriptor to the store if not already present.

        Emits ``selection_changed`` when the descriptor is newly added.

        Args:
            descriptor: The model descriptor to add.
        """
        key = ModelSelectionKey(provider_id=descriptor.provider_id, model_name=descriptor.model_name)
        if key not in self._items:
            self._items[key] = descriptor
            self.selection_changed.emit()

    def remove(self, key: ModelSelectionKey) -> None:
        """Remove a model by its composite key if present.

        Emits ``selection_changed`` when an entry is actually removed.

        Args:
            key: The composite key identifying the model to remove.
        """
        if key in self._items:
            del self._items[key]
            self.selection_changed.emit()

    def contains(self, key: ModelSelectionKey) -> bool:
        """Return True if the given key is currently selected.

        Args:
            key: The composite key to check.

        Returns:
            True when the key exists in the store, False otherwise.
        """
        return key in self._items

    def all(self) -> list[ModelDescriptor]:
        """Return all selected model descriptors in insertion order.

        Returns:
            List of all selected ModelDescriptor instances.
        """
        return list(self._items.values())

    def filter_by_provider(self, provider_id: str) -> list[ModelDescriptor]:
        """Return only descriptors belonging to the specified provider.

        Args:
            provider_id: The provider identifier to filter by.

        Returns:
            List of ModelDescriptor instances for the given provider.
        """
        return [d for d in self._items.values() if d.provider_id == provider_id]

    def clear_for_provider(self, provider_id: str) -> None:
        """Remove all selections for a specific provider.

        Emits ``selection_changed`` only when at least one entry is removed.

        Args:
            provider_id: The provider whose selections should be cleared.
        """
        keys_to_remove = [k for k in self._items if k.provider_id == provider_id]
        if keys_to_remove:
            for k in keys_to_remove:
                del self._items[k]
            self.selection_changed.emit()

    def clear_all(self) -> None:
        """Remove all selections from every provider.

        Emits ``selection_changed`` only when the store was non-empty.
        """
        if self._items:
            self._items.clear()
            self.selection_changed.emit()

    @property
    def count(self) -> int:
        """Return the total number of selected models across all providers."""
        return len(self._items)
