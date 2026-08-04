"""``NewBenchmarkController`` -- wires the Gateway, EventBus, and non-store helpers to
the view (STORY-054, STORY-055). Depends only on ``NewBenchmarkGateway`` plus the
declared non-store helpers (``EventBus``, ``ModeVisibilityPolicy``, ``RunValidator``)
-- never a backend Store/Service Protocol directly (D-R-06).
"""

import structlog

from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    ReadinessState,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    EventBus,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.ui.new_benchmark._internal.advanced_options import (
    AdvancedOptionsSectionWidget,
)
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark._internal.view_model_select import (
    NewBenchmarkViewState,
    RunStartRequestState,
    build_run_start_request,
    compute_start_button_state,
    select_view_model,
)
from ollama_llm_bench.ui.new_benchmark.models import (
    AdvancedOptionsViewModel,
    EmbeddingStatusViewModel,
    ValidationEntry,
)
from ollama_llm_bench.ui.new_benchmark.protocols import (
    ModeVisibilityPolicy,
    NewBenchmarkGateway,
    RunValidator,
)

__all__: list[str] = ["NewBenchmarkController"]

logger = structlog.get_logger(__name__)

_LAST_MODE_KEY = "benchmark.last_mode"
_DEFAULT_MODE = RunMode.SYNTHETIC
_EMBEDDING_PROVIDER_NAME_KEY = "embedding.selected_provider_name"
_EMBEDDING_MODEL_NAME_KEY = "embedding.selected_model_name"
_NO_MODEL_REACHABLE_MESSAGE = "No test model is reachable. Check provider settings."


class NewBenchmarkController:
    """Owns the New Benchmark widget's state: subscribes, derives, applies."""

    def __init__(
        self,
        *,
        gateway: NewBenchmarkGateway,
        event_bus: EventBus,
        mode_visibility_policy: ModeVisibilityPolicy,
        run_validator: RunValidator,
        view: NewBenchmarkView,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._policy = mode_visibility_policy
        self._run_validator = run_validator
        self._view = view
        self._provider_configs = {p.provider_id: p for p in gateway.provider_list()}
        self._is_locked = False
        self._gate_idle = True
        self._last_validation_entries: tuple[ValidationEntry, ...] = ()
        logger.debug("new_benchmark_controller_constructed")

    def bind(self) -> None:
        """Restore persisted state, wire signals, and render the initial ViewModel."""
        stored_mode = self._gateway.get_setting(_LAST_MODE_KEY)
        initial_mode = RunMode(stored_mode) if stored_mode else _DEFAULT_MODE
        self._current_mode = initial_mode
        self._view.mode_selector.set_mode(initial_mode)
        self._view.mode_selector.mode_changed.connect(self._on_mode_changed)
        self._view.task_files_section.rows_changed.connect(self._on_view_state_changed)
        self._view.test_models_section.selection_changed.connect(self._on_view_state_changed)
        self._view.judge_section.judge_config_changed.connect(self._on_view_state_changed)
        self._view.advanced_options_section.advanced_config_changed.connect(
            self._on_view_state_changed
        )
        self._view.performance_matrix_section.matrix_changed.connect(self._on_matrix_changed)
        self._view.start_button.clicked.connect(self._on_start_clicked)
        self._event_bus.subscribe(
            SIGNAL_PROVIDER_REGISTRY_RELOADED, self._on_provider_registry_reloaded, owner=self._view
        )
        self._event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED,
            self._on_inference_activity_changed,
            owner=self._view,
        )
        self._event_bus.subscribe(
            SIGNAL_APP_READINESS_CHANGED, self._on_readiness_changed, owner=self._view
        )
        self._event_bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_started, owner=self._view)
        self._event_bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_terminal, owner=self._view)
        self._event_bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_terminal, owner=self._view)
        self._event_bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_terminal, owner=self._view)
        self._view.judge_section.set_mode(initial_mode)
        self._view.advanced_options_section.set_grading_visible(initial_mode is RunMode.GRADED)
        self._render()

    def _on_mode_changed(self, mode: RunMode) -> None:
        if self._is_locked:
            return
        logger.debug("new_benchmark_mode_changed", mode=mode.value)
        self._gateway.set_setting(_LAST_MODE_KEY, mode.value)
        self._current_mode = mode
        self._view.judge_section.set_mode(mode)
        self._view.advanced_options_section.set_grading_visible(mode is RunMode.GRADED)
        self._render()

    def _on_provider_registry_reloaded(self, _payload: object) -> None:
        logger.debug("new_benchmark_provider_registry_reloaded")
        self._provider_configs = {p.provider_id: p for p in self._gateway.provider_list()}
        self._render()

    def _on_view_state_changed(self, *_args: object) -> None:
        if self._is_locked:
            return
        self._render()

    def _on_matrix_changed(self) -> None:
        if self._is_locked:
            return
        matrix = self._view.performance_matrix_section
        logger.debug(
            "new_benchmark_matrix_changed",
            input_size_count=len(matrix.selected_input_sizes),
            output_size_count=len(matrix.selected_output_sizes),
            repeats=matrix.repeats,
        )
        self._render()

    def _on_inference_activity_changed(self, payload: object) -> None:
        logger.debug("new_benchmark_inference_activity_changed")
        if isinstance(payload, InferenceActivityChangedEvent):
            self._gate_idle = payload.state.current is InferenceActivity.IDLE
        self._push_view_model(self._last_validation_entries)

    def _on_run_started(self, _payload: object) -> None:
        logger.debug("new_benchmark_run_started")
        self._is_locked = True

    def _on_run_terminal(self, _payload: object) -> None:
        logger.debug("new_benchmark_run_terminal")
        self._is_locked = False

    def _on_readiness_changed(self, _payload: object) -> None:
        """Re-render so the Start button reflects the new readiness (STORY-081-AC-2)."""
        self._render()

    def _on_start_clicked(self) -> None:
        if self._is_locked:
            return
        logger.debug("new_benchmark_start_clicked")
        # Deferred import (the sole sanctioned exception to "no late import inside a
        # function body"): ui.common_dialogs._internal.view_model_select needs
        # ui.new_benchmark.models (RunValidator/ValidationEntry, Design Decision 1),
        # so a module-level import here would make ui.new_benchmark's own package
        # __init__ chain (api.py -> this controller) transitively re-enter
        # ui.common_dialogs before it finishes initialising -- a genuine circular
        # import between the two packages. Deferring this single call-site import
        # to first-use (a user click, never import time) breaks the cycle without
        # touching compose.py or moving Design Decision 1's declared types.
        from ollama_llm_bench.ui.common_dialogs import (  # noqa: PLC0415
            make_run_summary_dialog,
        )

        request = self._build_current_run_start_request()
        dialog = make_run_summary_dialog(
            gateway=self._gateway,
            run_validator=self._run_validator,
            request=request,
            parent=self._view,
        )
        if dialog is None:
            logger.debug("new_benchmark_run_summary_dialog_refused")
            self._gateway.notify_error(_NO_MODEL_REACHABLE_MESSAGE)
            return
        dialog.exec()

    def _build_current_run_start_request(self) -> RunStartRequest:
        advanced_options = self._view.advanced_options_section
        dirty_keys = advanced_options.dirty_keys
        current_values = advanced_options.current_values
        matrix = self._view.performance_matrix_section
        state = RunStartRequestState(
            mode=self._current_mode,
            selected_pairs=self._view.test_models_section.selection.pairs,
            judge_provider_id=self._view.judge_section.judge_provider_id,
            judge_model=self._view.judge_section.judge_model,
            judge_analysis_enabled=self._view.judge_section.judge_analysis_enabled,
            task_paths=tuple(row.source_path for row in self._view.task_files_section.rows),
            input_sizes=matrix.selected_input_sizes,
            output_sizes=matrix.selected_output_sizes,
            repeats=matrix.repeats,
            advanced_options_overridden=advanced_options.override_enabled,
            advanced_dirty_values={
                key: value for key, value in current_values.items() if key in dirty_keys
            },
        )
        return build_run_start_request(state)

    def _embedding_status(self) -> EmbeddingStatusViewModel | None:
        if self._current_mode is not RunMode.GRADED:
            return None
        provider_display = self._gateway.get_setting(_EMBEDDING_PROVIDER_NAME_KEY)
        embedding_model = self._gateway.get_setting(_EMBEDDING_MODEL_NAME_KEY)
        readiness = self._gateway.readiness_snapshot()
        ready = bool(provider_display) and bool(embedding_model) and readiness.embedding_reachable
        return EmbeddingStatusViewModel(
            ready=ready,
            provider_display=provider_display or None,
            embedding_model=embedding_model or None,
        )

    def _render(self) -> None:
        request = self._build_current_run_start_request()
        self._last_validation_entries = self._run_validator.validate(request)
        self._push_view_model(self._last_validation_entries)

    def _push_view_model(self, validation_entries: tuple[ValidationEntry, ...]) -> None:
        readiness = self._gateway.readiness_snapshot()
        start_enabled, start_tooltip = compute_start_button_state(
            validation_entries=validation_entries,
            gate_idle=self._gate_idle,
            readiness_not_ready=readiness.overall is ReadinessState.NOT_READY,
        )
        advanced_options_section = self._view.advanced_options_section
        state = NewBenchmarkViewState(
            policy=self._policy,
            task_file_rows=self._view.task_files_section.rows,
            selection=self._view.test_models_section.selection,
            provider_configs=self._provider_configs,
            browsed_provider_id=self._view.test_models_section.browsed_provider_id,
            hide_embedding_models=self._view.test_models_section.hide_embedding_models,
            judge_analysis_enabled=self._view.judge_section.judge_analysis_enabled,
            judge_provider_id=self._view.judge_section.judge_provider_id,
            embedding_status=self._embedding_status(),
            advanced_options=_advanced_options_view_model(
                advanced_options_section, self._current_mode
            ),
            validation_entries=validation_entries,
            start_enabled=start_enabled,
            start_tooltip=start_tooltip,
            input_sizes=self._view.performance_matrix_section.selected_input_sizes,
            output_sizes=self._view.performance_matrix_section.selected_output_sizes,
            repeats=self._view.performance_matrix_section.repeats,
        )
        view_model = select_view_model(mode=self._current_mode, state=state)
        self._view.apply_view_model(view_model)


def _advanced_options_view_model(
    advanced_options_section: AdvancedOptionsSectionWidget, mode: RunMode
) -> AdvancedOptionsViewModel:
    return AdvancedOptionsViewModel(
        override_enabled=advanced_options_section.override_enabled,
        values=advanced_options_section.current_values,
        dirty_keys=advanced_options_section.dirty_keys,
        grading_visible=mode is RunMode.GRADED,
    )
