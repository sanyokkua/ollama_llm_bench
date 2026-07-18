"""``TestModelsSectionWidget`` -- the multi-provider Test Models section
(STORY-054-AC-3, AC-5).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §4.6,
``state_machine.md`` §3 (Empty -> Browsing -> SomeChecked -> MultiProvider). The
"browsed-provider dropdown" reuses ``ui.shared.provider_dropdown`` (STORY-052) via
a local ``ProviderListSource`` adapter; the "available models" toggle list and
"selected models summary" are custom controls (neither the reusable
model-dropdown nor multi-check-filter-button widget shapes fit a per-row
checkable list) -- see Design Decisions 6-7 in the story plan.
"""

from collections.abc import Callable
from typing import Protocol, cast

from PySide6.QtCore import Qt, Signal, SignalInstance
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.ui.new_benchmark._internal.selection_store import SelectionStore
from ollama_llm_bench.ui.shared.provider_dropdown import ProviderListSource, make_provider_dropdown

__all__: list[str] = ["TestModelsSectionWidget"]


class _ProviderChangedEmitter(Protocol):
    """Structural view of the provider-dropdown widget's public ``provider_changed`` signal.

    ``make_provider_dropdown`` returns a plain ``QWidget`` (its concrete type lives in
    ``ui.shared.provider_dropdown``'s private ``_internal``, which this module must not
    import -- see D-R-06/project-structure.md). This Protocol lets mypy narrow the
    returned widget to just the one signal this module actually calls, via ``cast``.
    """

    provider_changed: SignalInstance


class _GatewayBackedProviderListSource:
    """Adapts ``provider_configs_source`` to ``ProviderListSource`` (D-R-06 local shim)."""

    def __init__(self, provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]) -> None:
        self._source = provider_configs_source

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return tuple(p for p in self._source() if p.enabled)


class TestModelsSectionWidget(QWidget):
    """The Test Models section: hide-embedding toggle, provider browse, model toggles."""

    selection_changed = Signal()

    def __init__(
        self,
        *,
        provider_configs_source: Callable[[], tuple[ProviderConfig, ...]],
        hide_embedding_models_initial: bool,
        on_hide_embedding_changed: Callable[[bool], None],
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.test_models")
        self._provider_configs_source = provider_configs_source
        self._on_hide_embedding_changed = on_hide_embedding_changed
        self._hide_embedding_models = hide_embedding_models_initial
        self._browsed_provider_id: str | None = None
        self.selection = SelectionStore()
        self._build_ui(event_bus)

    def _build_ui(self, event_bus: EventBus | None) -> None:
        layout = QVBoxLayout(self)

        self._hide_embedding_checkbox = QCheckBox("Hide embedding models")
        self._hide_embedding_checkbox.setChecked(self._hide_embedding_models)
        self._hide_embedding_checkbox.toggled.connect(self._on_hide_embedding_toggled)
        layout.addWidget(self._hide_embedding_checkbox)

        provider_row = QHBoxLayout()
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setProperty("role", "outlined-muted-button")
        self._refresh_button.clicked.connect(self._refresh_available_models)
        provider_row.addWidget(self._refresh_button)
        layout.addLayout(provider_row)
        if event_bus is not None:
            provider_source: ProviderListSource = _GatewayBackedProviderListSource(
                self._provider_configs_source
            )
            provider_dropdown = make_provider_dropdown(
                provider_source=provider_source,
                event_bus=event_bus,
            )
            provider_dropdown.setObjectName("new_benchmark.test_models.provider_dropdown")
            cast("_ProviderChangedEmitter", provider_dropdown).provider_changed.connect(
                self.set_browsed_provider_for_test
            )
            layout.addWidget(provider_dropdown)

        self._available_list = QListWidget()
        self._available_list.setObjectName("new_benchmark.test_models.available_list")
        self._available_list.itemChanged.connect(self._on_available_item_changed)
        layout.addWidget(self._available_list)

        select_row = QHBoxLayout()
        self._select_all_button = QPushButton("Select All")
        self._select_all_button.setProperty("role", "outlined-muted-button")
        self._select_all_button.clicked.connect(self.click_select_all_for_test)
        self._clear_all_button = QPushButton("Clear All")
        self._clear_all_button.setProperty("role", "outlined-muted-button")
        self._clear_all_button.clicked.connect(self.click_clear_all_for_test)
        select_row.addWidget(self._select_all_button)
        select_row.addWidget(self._clear_all_button)
        layout.addLayout(select_row)

        self._summary_list = QListWidget()
        self._summary_list.setObjectName("new_benchmark.test_models.summary_list")
        self._summary_list.setMinimumHeight(120)
        self._summary_list.setMaximumHeight(240)
        layout.addWidget(self._summary_list)

    def _on_hide_embedding_toggled(self, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        self._hide_embedding_models = checked
        self._on_hide_embedding_changed(checked)
        self._refresh_available_models()

    def _current_provider_config(self) -> ProviderConfig | None:
        if self._browsed_provider_id is None:
            return None
        return next(
            (
                p
                for p in self._provider_configs_source()
                if p.provider_id == self._browsed_provider_id
            ),
            None,
        )

    def available_model_names_for_test(self) -> tuple[str, ...]:
        """Test helper: the browsed provider's model names after the hide-embedding filter."""
        config = self._current_provider_config()
        if config is None:
            return ()
        names = config.default_models
        if self._hide_embedding_models:
            names = tuple(n for n in names if not is_embedding_model(n))
        return names

    def set_browsed_provider_for_test(self, provider_id: str) -> None:
        """Test helper / signal target: switch the browsed provider and refresh the list."""
        self._browsed_provider_id = provider_id
        self._refresh_available_models()

    def _refresh_available_models(self) -> None:
        self._available_list.blockSignals(True)  # noqa: FBT003  # Qt boolean-parameter API
        self._available_list.clear()
        for name in self.available_model_names_for_test():
            item = QListWidgetItem(name)
            item.setCheckState(
                _checked_state(
                    self._browsed_provider_id is not None
                    and self.selection.contains(self._browsed_provider_id, name)
                )
            )
            self._available_list.addItem(item)
        self._available_list.blockSignals(False)  # noqa: FBT003  # Qt boolean-parameter API

    def _on_available_item_changed(self, item: QListWidgetItem) -> None:
        if self._browsed_provider_id is None:
            return
        model_name = item.text()
        if item.checkState().value:
            self.selection.add(self._browsed_provider_id, model_name)
        else:
            self.selection.remove(self._browsed_provider_id, model_name)
        self._refresh_summary()
        self.selection_changed.emit()

    def toggle_model_for_test(self, model_name: str) -> None:
        """Test helper: simulate a user click toggling ``model_name`` in the available list."""
        for row in range(self._available_list.count()):
            item = self._available_list.item(row)
            if item.text() == model_name:
                item.setCheckState(_checked_state(not item.checkState().value))
                return
        raise AssertionError(f"{model_name!r} is not in the available-models list")

    def click_select_all_for_test(self) -> None:
        """Select every currently-available model for the browsed provider."""
        if self._browsed_provider_id is None:
            return
        for name in self.available_model_names_for_test():
            self.selection.add(self._browsed_provider_id, name)
        self._refresh_available_models()
        self._refresh_summary()
        self.selection_changed.emit()

    def click_clear_all_for_test(self) -> None:
        """Clear every selected pair for the browsed provider only (AC-5)."""
        if self._browsed_provider_id is None:
            return
        self.selection.clear_provider(self._browsed_provider_id)
        self._refresh_available_models()
        self._refresh_summary()
        self.selection_changed.emit()

    def _refresh_summary(self) -> None:
        self._summary_list.clear()
        provider_names = {p.provider_id: p.name for p in self._provider_configs_source()}
        pairs = self.selection.pairs
        header = f"Selected models ({len(pairs)} across {self.selection.provider_count} providers)"
        self._summary_list.addItem(header)
        for provider_id, model_name in pairs:
            provider_name = provider_names.get(provider_id, provider_id)
            self._summary_list.addItem(f"{provider_name} · {model_name}")


def _checked_state(checked: bool) -> Qt.CheckState:  # noqa: FBT001  # thin Qt.CheckState mapper
    return Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
