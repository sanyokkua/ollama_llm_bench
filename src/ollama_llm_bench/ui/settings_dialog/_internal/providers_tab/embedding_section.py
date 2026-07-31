"""``EmbeddingSectionWidget`` -- the single embedding-model selection pair (the
shared provider/model dropdowns, the Show-all-models filter toggle, and Test
Embedding), initialised from the persisted embedding selection or the
first-start bootstrap (``description.md`` §3.4, §14).

Composes the shared ``ui/shared/model_dropdown``'s ``filter=`` the same way
``ui/common_dialogs``'s ``GenerateAnalysisDialog`` composes it with
``backend.model_helpers.is_embedding_model`` -- there to *exclude* embedding
models; here to *include only* embedding-likely models when Show all models is
off. There is no built-in "show all models" toggle on the shared widget itself
(``ui/shared/provider_dropdown``/``model_dropdown`` take only a caller-supplied
``filter``), so the toggle is composed locally as a mutable closure the model
dropdown's filter reads on every repopulate.

Takes a ``EmbeddingSectionCollaborators`` bundle of plain callables rather than
the whole ``SettingsGateway`` -- mirrors
``ui.new_benchmark._internal.judge_section``'s ``_GatewayBackedProviderListSource``/
``_GatewayBackedModelFetcher`` local-shim pattern (D-R-06): this widget never
holds the gateway Protocol itself, only the bound methods it actually calls.

The Test Embedding button and the persisted-selection/first-start-bootstrap
initialisation were added in a STORY-066 spec-conformance fix pass (§3.4, §14
were previously undelivered although both were in this story's declared scope).
"""

from collections.abc import Callable
import functools
from typing import Protocol, cast

from PySide6.QtCore import QSignalBlocker, SignalInstance
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget
import structlog

from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    ModelName,
    ProviderConfig,
    ProviderId,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_select import (
    gate_button_state,
)
from ollama_llm_bench.ui.settings_dialog._internal.view_model_select import (
    find_provider_id_by_name,
)
from ollama_llm_bench.ui.settings_dialog.models import EmbeddingSectionCollaborators
from ollama_llm_bench.ui.settings_dialog.protocols import DiscoverModelsCallable
from ollama_llm_bench.ui.shared.model_dropdown import make_model_dropdown
from ollama_llm_bench.ui.shared.provider_dropdown import make_provider_dropdown

__all__: list[str] = ["EmbeddingSectionWidget"]

logger = structlog.get_logger(__name__)

_SELECTED_PROVIDER_NAME_KEY = "embedding.selected_provider_name"
_SELECTED_MODEL_NAME_KEY = "embedding.selected_model_name"


class _ComboSelectable(Protocol):
    """Structural view of the shared dropdown widgets' real ``QComboBox`` surface."""

    def findData(self, value: object) -> int: ...
    def findText(self, text: str) -> int: ...
    def setCurrentIndex(self, index: int) -> None: ...
    def currentData(self) -> object: ...
    def currentText(self) -> str: ...


class _SetProvider(Protocol):
    """Structural view of the model-dropdown widget's public ``set_provider`` method."""

    def set_provider(self, provider_id: str) -> None: ...


class _ProviderChangedEmitter(Protocol):
    """Structural view of the provider dropdown's public ``provider_changed`` signal."""

    provider_changed: SignalInstance


class _GatewayBackedProviderListSource:
    """Adapts ``provider_configs_source`` to ``ProviderListSource`` (D-R-06 local shim)."""

    def __init__(self, provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]) -> None:
        self._source = provider_configs_source

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return tuple(p for p in self._source() if p.enabled)


class _DiscoverModelsFetcher:
    """Adapts ``discover_models`` to ``ModelFetcher`` (D-R-06 local shim).

    ``SettingsGateway.discover_models`` names no ``Raises`` category in its
    contract (08-E §7b.6, §1: "a method whose contract names no category does
    not raise ... it returns a value or a status instead"), so this shim never
    needs an error path of its own; ``on_error`` is accepted only to satisfy
    ``ModelFetcher``'s shape. ``discover_models`` itself returns ``None``
    immediately and delivers via ``on_complete`` (ADR-0015, STORY-110) --
    this shim's own ``on_success`` becomes that ``on_complete`` callback,
    closed over ``provider_id`` so ``ModelFetcher``'s two-argument shape is
    preserved for ``model_dropdown``.
    """

    def __init__(self, discover_models: DiscoverModelsCallable) -> None:
        self._discover_models = discover_models

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],  # noqa: ARG002  # Protocol shape only -- discover_models never raises for an expected failure
    ) -> None:
        self._discover_models(provider_id, on_complete=functools.partial(on_success, provider_id))


class EmbeddingSectionWidget(QWidget):
    """The embedding provider/model pickers, Show-all-models toggle, and Test
    Embedding diagnostic (§3.4), initialised from the persisted selection or
    the first-start bootstrap (§14)."""

    def __init__(self, *, collaborators: EmbeddingSectionCollaborators) -> None:
        super().__init__()
        self.setObjectName("settings_dialog.embedding_section")
        self._show_all = False
        self._probe_embedding = collaborators.probe_embedding
        self._discover_models = collaborators.discover_models
        self._gate_activity = InferenceActivity.IDLE
        self._build_ui(collaborators=collaborators)
        self._initialize_selection(collaborators=collaborators)
        collaborators.event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED, self._on_inference_activity_changed, owner=self
        )
        logger.debug("embedding_section_constructed")

    def _build_ui(self, *, collaborators: EmbeddingSectionCollaborators) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Embedding model")
        title.setProperty("role", "section-title")
        layout.addWidget(title)

        self._provider_dropdown = make_provider_dropdown(
            provider_source=_GatewayBackedProviderListSource(collaborators.provider_configs_source),
            event_bus=collaborators.event_bus,
        )
        self._provider_dropdown.setObjectName("settings_dialog.embedding_section.provider_dropdown")
        cast("_ProviderChangedEmitter", self._provider_dropdown).provider_changed.connect(
            self._on_provider_changed
        )
        layout.addWidget(self._provider_dropdown)

        self._model_dropdown = make_model_dropdown(
            model_fetcher=_DiscoverModelsFetcher(collaborators.discover_models),
            filter=lambda name: self._show_all or is_embedding_model(name),
        )
        self._model_dropdown.setObjectName("settings_dialog.embedding_section.model_dropdown")
        layout.addWidget(self._model_dropdown)

        self._show_all_checkbox = QCheckBox("Show all models")
        self._show_all_checkbox.setObjectName("settings_dialog.embedding_section.show_all")
        self._show_all_checkbox.toggled.connect(self._on_show_all_toggled)
        layout.addWidget(self._show_all_checkbox)

        self._test_embedding_button = QPushButton("Test Embedding")
        self._test_embedding_button.setObjectName(
            "settings_dialog.embedding_section.test_embedding"
        )
        self._test_embedding_button.clicked.connect(self._on_test_embedding_clicked)
        layout.addWidget(self._test_embedding_button)

        self._diagnostic_label = QLabel("")
        self._diagnostic_label.setObjectName("settings_dialog.embedding_section.diagnostic")
        self._diagnostic_label.setWordWrap(True)
        layout.addWidget(self._diagnostic_label)

    def _initialize_selection(self, *, collaborators: EmbeddingSectionCollaborators) -> None:
        """Preselect the dropdowns from the persisted embedding selection, or
        run the first-start bootstrap search when nothing is persisted (§1.4, §14)."""
        providers = collaborators.provider_configs_source()
        persisted_provider_name = collaborators.get_setting(_SELECTED_PROVIDER_NAME_KEY)
        persisted_model_name = collaborators.get_setting(_SELECTED_MODEL_NAME_KEY)
        provider_id = (
            find_provider_id_by_name(providers=providers, name=persisted_provider_name)
            if persisted_provider_name
            else None
        )
        if provider_id is not None:
            self._select_provider_and_populate_models(provider_id)
            if persisted_model_name:
                self._select_model_if_present(persisted_model_name)
            logger.debug(
                "embedding_section_initialized_from_persisted_selection", provider_id=provider_id
            )
            return
        enabled_providers = tuple(p for p in providers if p.enabled)
        self._bootstrap_search_next(enabled_providers, 0)

    def _bootstrap_search_next(
        self, enabled_providers: tuple[ProviderConfig, ...], index: int
    ) -> None:
        """Walk ``enabled_providers`` one at a time for the first-start
        embedding bootstrap search (§14).

        ``discover_models`` is fast-synchronous and delivers via
        ``on_complete`` (ADR-0015, STORY-110) -- it no longer returns a
        value the former ``resolve_embedding_bootstrap_pair`` pure function
        could walk over synchronously, so this method chains one provider's
        discovery into the next's via callbacks instead, preserving the same
        "first embedding-likely model, in provider order" search semantics.
        """
        if index >= len(enabled_providers):
            logger.debug("embedding_section_bootstrap_found_no_embedding_model")
            return
        provider = enabled_providers[index]
        self._discover_models(
            provider.provider_id,
            on_complete=functools.partial(
                self._on_bootstrap_models_discovered, enabled_providers, index
            ),
        )

    def _on_bootstrap_models_discovered(
        self,
        enabled_providers: tuple[ProviderConfig, ...],
        index: int,
        models: tuple[ModelName, ...],
    ) -> None:
        provider = enabled_providers[index]
        embedding_model = next((model for model in models if is_embedding_model(model)), None)
        if embedding_model is None:
            self._bootstrap_search_next(enabled_providers, index + 1)
            return
        self._select_provider_and_populate_models(provider.provider_id)
        self._select_model_if_present(embedding_model)
        logger.debug(
            "embedding_section_bootstrap_selected",
            provider_id=provider.provider_id,
            model_name=embedding_model,
        )

    def _select_provider_and_populate_models(self, provider_id: str) -> None:
        combo = cast("_ComboSelectable", self._provider_dropdown)
        index = combo.findData(provider_id)
        if index >= 0:
            with QSignalBlocker(self._provider_dropdown):
                combo.setCurrentIndex(index)
        cast("_SetProvider", self._model_dropdown).set_provider(provider_id)

    def _select_model_if_present(self, model_name: str) -> None:
        combo = cast("_ComboSelectable", self._model_dropdown)
        index = combo.findText(model_name)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _on_provider_changed(self, provider_id: str) -> None:
        cast("_SetProvider", self._model_dropdown).set_provider(provider_id)

    def _on_show_all_toggled(self, checked: bool) -> None:  # noqa: FBT001  # Qt's own toggled(bool) signal signature
        self._show_all = checked
        current_provider = cast("_ComboSelectable", self._provider_dropdown).currentData()
        if isinstance(current_provider, str):
            # Re-triggers the same fetch so the filter closure is re-applied to
            # the same dynamic list -- description.md §3.4: "Toggling it only
            # re-populates the Model dropdown from the same dynamic list."
            cast("_SetProvider", self._model_dropdown).set_provider(current_provider)

    def _on_inference_activity_changed(self, payload: object) -> None:
        if not isinstance(payload, InferenceActivityChangedEvent):
            return
        self._gate_activity = payload.state.current
        self._refresh_test_embedding_button_state()

    def _refresh_test_embedding_button_state(self) -> None:
        enabled, tooltip = gate_button_state(self._gate_activity)
        self._test_embedding_button.setEnabled(enabled)
        self._test_embedding_button.setToolTip(tooltip)

    def _on_test_embedding_clicked(self) -> None:
        logger.debug("embedding_section_test_embedding_clicked")
        self.set_diagnostic("Testing…")
        self._probe_embedding()
        # The real outcome arrives via the existing _app_readiness_changed
        # subscription (SettingsController._on_readiness_changed ->
        # ProvidersTabController.apply_embedding_diagnostic -> set_diagnostic),
        # not from this call's return value (ADR-0015, STORY-110) -- probe_embedding
        # returns None immediately and the concrete gateway publishes the event
        # itself once the billable capability check settles.

    def set_diagnostic(self, text: str) -> None:
        """Render the last Test Embedding result, redacted for display."""
        self._diagnostic_label.setText(text)

    def selected_pair(self) -> tuple[str | None, str | None]:
        """Return the currently selected ``(provider_id, model_name)`` pair."""
        provider_id = cast("_ComboSelectable", self._provider_dropdown).currentData()
        model_name = cast("_ComboSelectable", self._model_dropdown).currentText()
        return (
            provider_id if isinstance(provider_id, str) else None,
            model_name or None,
        )
