"""``JudgeSectionWidget`` -- the Judge section: analysis toggle, provider/model
dropdowns, Refresh, and the ``GRADED``-only embedding status row (STORY-055-AC-1,
AC-2).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §4.4 (per-mode default
and greyed/hidden dropdown rule), §4.5 (embedding status row). The Judge Provider
and Judge Model dropdowns reuse ``ui.shared.provider_dropdown``/``ui.shared.model_dropdown``
(STORY-051/STORY-052) via the same local shim pattern ``_internal/test_models.py``
uses for the Test Models section's provider dropdown (D-R-06 -- no adapter shim
required, structural satisfaction).
"""

from collections.abc import Callable
from typing import Protocol, cast

from PySide6.QtCore import Signal, SignalInstance
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import ModelName, ProviderConfig, ProviderId, RunMode
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.ui.new_benchmark.models import EmbeddingStatusViewModel
from ollama_llm_bench.ui.shared.model_dropdown import ModelFetcher, make_model_dropdown
from ollama_llm_bench.ui.shared.provider_dropdown import ProviderListSource, make_provider_dropdown

__all__: list[str] = ["JudgeSectionWidget"]

_ANALYSIS_DEFAULT_ON_MODES: frozenset[RunMode] = frozenset({RunMode.GRADED})


class _ProviderChangedEmitter(Protocol):
    """Structural view of the provider-dropdown widget's public ``provider_changed`` signal.

    Mirrors ``_internal/test_models.py``'s ``_ProviderChangedEmitter`` -- see that
    module's docstring for why this cast-only Protocol exists (D-R-06).
    """

    provider_changed: SignalInstance


class _ModelChangedEmitter(Protocol):
    """Structural view of the model-dropdown widget's public ``model_changed`` signal."""

    model_changed: SignalInstance


class _GatewayBackedProviderListSource:
    """Adapts ``provider_configs_source`` to ``ProviderListSource`` (D-R-06 local shim)."""

    def __init__(self, provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]) -> None:
        self._source = provider_configs_source

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return tuple(p for p in self._source() if p.enabled)


class _GatewayBackedModelFetcher:
    """Adapts ``provider_configs_source`` to ``ModelFetcher`` (D-R-06 local shim).

    ``ProviderConfig.default_models`` is each provider's already-fetched manual
    model list (`08-E` §7.4); resolving it needs no network call and completes
    synchronously, so both callback branches fire before ``fetch_models`` returns.
    """

    def __init__(self, provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]) -> None:
        self._source = provider_configs_source

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        config = next((p for p in self._source() if p.provider_id == provider_id), None)
        if config is None:
            on_error(provider_id, ValueError(f"provider {provider_id!r} is not known"))
            return
        on_success(provider_id, config.default_models)


class JudgeSectionWidget(QWidget):
    """The Judge section: analysis toggle, provider/model dropdowns, embedding status row."""

    judge_config_changed = Signal()

    def __init__(
        self,
        *,
        provider_configs_source: Callable[[], tuple[ProviderConfig, ...]],
        hide_embedding_models_source: Callable[[], bool],
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.judge")
        self._provider_configs_source = provider_configs_source
        self._hide_embedding_models_source = hide_embedding_models_source
        self._current_mode = RunMode.SYNTHETIC
        self._provider_dropdown: QWidget | None = None
        self._model_dropdown: QWidget | None = None
        self._build_ui(event_bus)

    def _build_ui(self, event_bus: EventBus | None) -> None:
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        title = QLabel("Judge")
        title.setProperty("role", "section-title")
        header_row.addWidget(title)
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setObjectName("judge_model_refresh_button")
        self._refresh_button.setProperty("role", "outlined-muted-button")
        self._refresh_button.setAccessibleName("Refresh judge model list")
        self._refresh_button.setToolTip("Refresh the judge provider's model list")
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        header_row.addWidget(self._refresh_button)
        layout.addLayout(header_row)

        self._analysis_checkbox = QCheckBox("Generate run analysis for this run")
        self._analysis_checkbox.setObjectName("new_benchmark.judge.analysis_checkbox")
        self._analysis_checkbox.setProperty("role", "toggle")
        self._analysis_checkbox.setAccessibleName("Generate run analysis for this run")
        self._analysis_checkbox.toggled.connect(self._on_analysis_toggled)
        layout.addWidget(self._analysis_checkbox)

        if event_bus is not None:
            self._build_dropdowns(layout, event_bus)

        self.embedding_status_row = QLabel()
        self.embedding_status_row.setObjectName("new_benchmark.judge.embedding_status")
        self.embedding_status_row.setWordWrap(True)
        layout.addWidget(self.embedding_status_row)

    def _build_dropdowns(self, layout: QVBoxLayout, event_bus: EventBus) -> None:
        provider_source: ProviderListSource = _GatewayBackedProviderListSource(
            self._provider_configs_source
        )
        provider_dropdown = make_provider_dropdown(
            provider_source=provider_source, event_bus=event_bus
        )
        provider_dropdown.setObjectName("new_benchmark.judge.provider_dropdown")
        cast("_ProviderChangedEmitter", provider_dropdown).provider_changed.connect(
            self._on_provider_changed
        )
        layout.addWidget(provider_dropdown)
        self._provider_dropdown = provider_dropdown

        model_fetcher: ModelFetcher = _GatewayBackedModelFetcher(self._provider_configs_source)
        model_dropdown = make_model_dropdown(model_fetcher=model_fetcher, filter=self._model_filter)
        model_dropdown.setObjectName("new_benchmark.judge.model_dropdown")
        cast("_ModelChangedEmitter", model_dropdown).model_changed.connect(self._on_model_changed)
        layout.addWidget(model_dropdown)
        self._model_dropdown = model_dropdown

        # The provider dropdown auto-selects its first item under a QSignalBlocker at
        # construction (ui.shared.provider_dropdown), so that initial selection never
        # reaches provider_changed. Force one initial sync so the model dropdown
        # reflects whichever provider is already selected, without waiting for a
        # genuine user re-selection.
        initial_provider_id = cast("_CurrentDataReader", provider_dropdown).currentData()
        if isinstance(initial_provider_id, str):
            self._on_provider_changed(initial_provider_id)

    def _model_filter(self, model_name: ModelName) -> bool:
        """Exclude embedding-style models, intersected with the hide-embedding setting."""
        return not (self._hide_embedding_models_source() and is_embedding_model(model_name))

    @property
    def judge_analysis_enabled(self) -> bool:
        """The "Generate run analysis for this run" toggle's current state."""
        return self._analysis_checkbox.isChecked()

    @property
    def judge_provider_id(self) -> str | None:
        """The currently selected Judge Provider id, or ``None``."""
        if self._provider_dropdown is None:
            return None
        data = cast("_CurrentDataReader", self._provider_dropdown).currentData()
        return data if isinstance(data, str) else None

    @property
    def judge_model(self) -> str | None:
        """The currently selected Judge Model name, or ``None``.

        Read from the combo's own ``currentText()`` rather than tracked purely
        from ``model_changed`` -- the model dropdown auto-selects its first item
        under a ``QSignalBlocker`` on every ``set_provider`` call, so that
        selection never reaches ``_on_model_changed``.
        """
        if self._model_dropdown is None:
            return None
        text = cast("_CurrentTextReader", self._model_dropdown).currentText()
        return text or None

    def set_mode(self, mode: RunMode) -> None:
        """Reset the analysis toggle to ``mode``'s default and re-apply the
        greyed/hidden dropdown rule (§4.4; STORY-055-AC-1)."""
        self._current_mode = mode
        self._analysis_checkbox.blockSignals(True)  # noqa: FBT003  # Qt boolean-parameter API
        self._analysis_checkbox.setChecked(mode in _ANALYSIS_DEFAULT_ON_MODES)
        self._analysis_checkbox.blockSignals(False)  # noqa: FBT003  # Qt boolean-parameter API
        self._apply_dropdown_display_rule()

    def apply_embedding_status(self, view_model: EmbeddingStatusViewModel | None) -> None:
        """Render the embedding status row from ``view_model`` (§4.5); ``None`` clears it."""
        if view_model is None:
            self.embedding_status_row.clear()
            self.embedding_status_row.setProperty("role", "")
            return
        if view_model.ready:
            self.embedding_status_row.setProperty("role", "success-badge")
            self.embedding_status_row.setText(
                f"Embedding: {view_model.provider_display} · {view_model.embedding_model} "
                "— ready for keyword-semantic and cosine validation."
            )
        else:
            self.embedding_status_row.setProperty("role", "warning-badge")
            self.embedding_status_row.setText(
                "No embedding model configured or reachable. Configure one in Settings."
            )

    def _on_analysis_toggled(self, _checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        self._apply_dropdown_display_rule()
        self.judge_config_changed.emit()

    def _apply_dropdown_display_rule(self) -> None:
        """The one legitimate greyed case (SYNTHETIC) plus the TASKS hidden case (§12)."""
        if self._current_mode is RunMode.SYNTHETIC:
            visible, enabled = True, self.judge_analysis_enabled
        elif self._current_mode is RunMode.TASKS:
            visible, enabled = self.judge_analysis_enabled, True
        else:
            visible, enabled = True, True
        for dropdown in (self._provider_dropdown, self._model_dropdown):
            if dropdown is not None:
                dropdown.setVisible(visible)
                dropdown.setEnabled(enabled)

    def _on_provider_changed(self, provider_id: str) -> None:
        if self._model_dropdown is not None:
            cast("_SetProvider", self._model_dropdown).set_provider(provider_id)
        self.judge_config_changed.emit()

    def _on_model_changed(self, _model_name: str) -> None:
        self.judge_config_changed.emit()

    def _on_refresh_clicked(self) -> None:
        provider_id = self.judge_provider_id
        if provider_id is not None and self._model_dropdown is not None:
            cast("_SetProvider", self._model_dropdown).set_provider(provider_id)


class _SetProvider(Protocol):
    """Structural view of the model-dropdown widget's public ``set_provider`` method."""

    def set_provider(self, provider_id: str) -> None: ...


class _CurrentDataReader(Protocol):
    """Structural view of ``QComboBox.currentData`` -- the provider dropdown's real type."""

    def currentData(self) -> object: ...


class _CurrentTextReader(Protocol):
    """Structural view of ``QComboBox.currentText`` -- the model dropdown's real type."""

    def currentText(self) -> str: ...
