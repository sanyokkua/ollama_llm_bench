"""``NewBenchmarkController`` -- wires the Gateway, EventBus, and non-store helpers to
the view (STORY-054). Depends only on ``NewBenchmarkGateway`` plus the declared
non-store helpers (``EventBus``, ``ModeVisibilityPolicy``) -- never a backend
Store/Service Protocol directly (D-R-06).
"""

import structlog

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import SIGNAL_PROVIDER_REGISTRY_RELOADED, EventBus
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark._internal.view_model_select import (
    NewBenchmarkViewState,
    select_view_model,
)
from ollama_llm_bench.ui.new_benchmark.protocols import ModeVisibilityPolicy, NewBenchmarkGateway

__all__: list[str] = ["NewBenchmarkController"]

logger = structlog.get_logger(__name__)

_LAST_MODE_KEY = "benchmark.last_mode"
_DEFAULT_MODE = RunMode.SYNTHETIC


class NewBenchmarkController:
    """Owns the New Benchmark widget's state: subscribes, derives, applies."""

    def __init__(
        self,
        *,
        gateway: NewBenchmarkGateway,
        event_bus: EventBus,
        mode_visibility_policy: ModeVisibilityPolicy,
        view: NewBenchmarkView,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._policy = mode_visibility_policy
        self._view = view
        self._provider_configs = {p.provider_id: p for p in gateway.provider_list()}
        logger.debug("new_benchmark_controller_constructed")

    def bind(self) -> None:
        """Restore persisted state, wire signals, and render the initial ViewModel."""
        stored_mode = self._gateway.get_setting(_LAST_MODE_KEY)
        initial_mode = RunMode(stored_mode) if stored_mode else _DEFAULT_MODE
        self._view.mode_selector.set_mode(initial_mode)
        self._view.mode_selector.mode_changed.connect(self._on_mode_changed)
        self._view.task_files_section.rows_changed.connect(self._on_view_state_changed)
        self._view.test_models_section.selection_changed.connect(self._on_view_state_changed)
        self._event_bus.subscribe(
            SIGNAL_PROVIDER_REGISTRY_RELOADED, self._on_provider_registry_reloaded, owner=self._view
        )
        self._current_mode = initial_mode
        self._render()

    def _on_mode_changed(self, mode: RunMode) -> None:
        logger.debug("new_benchmark_mode_changed", mode=mode.value)
        self._gateway.set_setting(_LAST_MODE_KEY, mode.value)
        self._current_mode = mode
        self._render()

    def _on_provider_registry_reloaded(self, _payload: object) -> None:
        logger.debug("new_benchmark_provider_registry_reloaded")
        self._provider_configs = {p.provider_id: p for p in self._gateway.provider_list()}
        self._render()

    def _on_view_state_changed(self, *_args: object) -> None:
        self._render()

    def _render(self) -> None:
        state = NewBenchmarkViewState(
            policy=self._policy,
            task_file_rows=self._view.task_files_section.rows,
            selection=self._view.test_models_section.selection,
            provider_configs=self._provider_configs,
            browsed_provider_id=self._view.test_models_section.browsed_provider_id,
            hide_embedding_models=self._view.test_models_section.hide_embedding_models,
        )
        view_model = select_view_model(mode=self._current_mode, state=state)
        self._view.apply_view_model(view_model)
