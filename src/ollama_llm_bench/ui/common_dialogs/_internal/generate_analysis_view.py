"""``GenerateAnalysisDialog`` -- the Generate/Regenerate Analysis modal (STORY-065-AC-5,
AC-6, AC-7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/generate_analysis_dialog.md``
§3 (layout), §4 (provider/model selection), §5 (default selection), §6 (filter rule),
§8 (confirm behaviour and the single-inference gate), §8.1 (live progress line), §9
(cancel behaviour), §10 (state machine). Presents and dispatches only -- it never calls
an analysis model itself; ``RunAnalysisDispatcher.regenerate_analysis`` does.

Two documented scope simplifications (out of this story's ``acceptance_criteria``/
``edge_cases``, both scoped to EC-GA-8/the ``JudgeTimeoutExhausted`` sub-state which
this story does not cite):

- The dialog does not distinguish a generic failure from the role=JUDGE
  adaptive-timeout-exhaustion failure (EC-GA-8) -- both close the dialog the same way,
  via the gate returning to ``IDLE``; the Run Analysis tab surfaces the classified
  reason either way (§8 step 4/§9). The ``JudgeTimeoutExhausted`` stay-open sub-state
  (§10) is not implemented.
- The open-time gate-busy empty states (EC-GA-1/2/3/4/7) are not separately modelled;
  this dialog always opens for inspection and gates purely on Confirm (§8 step 4,
  AC-6), which is this story's tested contract.
"""

from typing import Protocol, cast

from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    InferenceActivity,
    InferenceContext,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    SIGNAL_INFERENCE_PROGRESS,
    SIGNAL_RUN_ANALYSIS_RECEIVED,
    InferenceActivityChangedEvent,
    InferenceProgressEvent,
    RunAnalysisReceivedEvent,
)
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.ui.common_dialogs._internal.generate_analysis_select import (
    default_provider_id,
    resolve_title_and_button_label,
)
from ollama_llm_bench.ui.common_dialogs.models import GenerateAnalysisCollaborators
from ollama_llm_bench.ui.shared.model_dropdown import ModelFetcher, make_model_dropdown
from ollama_llm_bench.ui.shared.provider_dropdown import make_provider_dropdown

__all__: list[str] = ["GenerateAnalysisDialog"]

logger = structlog.get_logger(__name__)

_EXPLANATION = (
    "Generating the run analysis will call the chosen model once against the run's "
    "results. The chosen pair is used only for this call; the run's snapshot is not "
    "modified."
)
_GATE_BUSY_MESSAGE = "An inference is currently in flight — please wait."
_GATE_BUSY_TOOLTIP = "Another inference activity is in flight — please wait."


class _ComboSelectable(Protocol):
    """Structural view of the shared dropdown widgets' real ``QComboBox`` surface."""

    def findData(self, value: object) -> int: ...
    def setCurrentIndex(self, index: int) -> None: ...
    def currentData(self) -> object: ...
    def currentText(self) -> str: ...


class _ProviderChangedEmitter(Protocol):
    """Structural view of the provider dropdown's public ``provider_changed`` signal."""

    provider_changed: SignalInstance


class GenerateAnalysisDialog(QDialog):
    """The Generate/Regenerate Analysis modal: provider/model pick, Confirm, gate-busy."""

    def __init__(
        self,
        *,
        run: BenchmarkRun,
        collaborators: GenerateAnalysisCollaborators,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.generate_analysis")
        self._run = run
        self._dispatcher = collaborators.dispatcher
        self._provider_source = collaborators.provider_source
        self._event_bus = collaborators.event_bus
        self._settled = False
        event_bus = collaborators.event_bus
        self._gate_subscription = event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED, self._on_inference_activity_changed
        )
        self._progress_subscription = event_bus.subscribe(
            SIGNAL_INFERENCE_PROGRESS, self._on_inference_progress
        )
        self._analysis_subscription = event_bus.subscribe(
            SIGNAL_RUN_ANALYSIS_RECEIVED, self._on_run_analysis_received
        )
        self._build_ui(collaborators.model_fetcher)
        self._apply_default_selection()
        logger.debug("generate_analysis_dialog_constructed", run_id=run.run_id)

    def _build_ui(self, model_fetcher: ModelFetcher) -> None:
        title, button_label = resolve_title_and_button_label(run=self._run)
        self.setWindowTitle(title)
        outer = QVBoxLayout(self)

        self._fields_container = QWidget()
        fields_layout = QVBoxLayout(self._fields_container)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        self._provider_dropdown = make_provider_dropdown(
            provider_source=self._provider_source, event_bus=self._event_bus
        )
        self._provider_dropdown.setObjectName("common_dialogs.generate_analysis.provider_dropdown")
        cast("_ProviderChangedEmitter", self._provider_dropdown).provider_changed.connect(
            self._on_provider_changed
        )
        fields_layout.addWidget(self._provider_dropdown)
        self._model_dropdown = make_model_dropdown(
            model_fetcher=model_fetcher, filter=lambda name: not is_embedding_model(name)
        )
        self._model_dropdown.setObjectName("common_dialogs.generate_analysis.model_dropdown")
        fields_layout.addWidget(self._model_dropdown)
        explanation = QLabel(_EXPLANATION)
        explanation.setWordWrap(True)
        fields_layout.addWidget(explanation)
        outer.addWidget(self._fields_container)

        self._busy_label = QLabel(_GATE_BUSY_MESSAGE)
        self._busy_label.setObjectName("common_dialogs.generate_analysis.busy_label")
        self._busy_label.setProperty("role", "info-callout")
        self._busy_label.setWordWrap(True)
        self._busy_label.setVisible(False)
        outer.addWidget(self._busy_label)

        self._progress_label = QLabel("")
        self._progress_label.setObjectName("common_dialogs.generate_analysis.progress_label")
        self._progress_label.setVisible(False)
        outer.addWidget(self._progress_label)

        outer.addLayout(self._build_footer(button_label))

    def _build_footer(self, button_label: str) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.setProperty("role", "outlined-muted-button")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        self._confirm_button = QPushButton(button_label)
        self._confirm_button.setObjectName("common_dialogs.generate_analysis.confirm_button")
        self._confirm_button.setProperty("role", "primary-button")
        self._confirm_button.setDefault(True)
        self._confirm_button.clicked.connect(self._on_confirm_clicked)
        footer.addWidget(self._confirm_button)
        return footer

    def _apply_default_selection(self) -> None:
        provider_dropdown = cast("_ComboSelectable", self._provider_dropdown)
        provider_ids = tuple(p.provider_id for p in self._provider_source.list_enabled())
        default_id = default_provider_id(run=self._run, enabled_provider_ids=provider_ids)
        current = provider_dropdown.currentData()
        if default_id is not None and default_id != current:
            index = provider_dropdown.findData(default_id)
            if index >= 0:
                provider_dropdown.setCurrentIndex(index)
                return
        if isinstance(current, str):
            self._on_provider_changed(current)

    def _current_provider_id(self) -> ProviderId | None:
        data = cast("_ComboSelectable", self._provider_dropdown).currentData()
        return data if isinstance(data, str) else None

    def _current_model_name(self) -> ModelName | None:
        text = cast("_ComboSelectable", self._model_dropdown).currentText()
        return text or None

    def _on_provider_changed(self, provider_id: str) -> None:
        cast("_SetProvider", self._model_dropdown).set_provider(provider_id)

    def _on_confirm_clicked(self) -> None:
        provider_id = self._current_provider_id()
        model_name = self._current_model_name()
        if provider_id is None or model_name is None:
            return
        logger.debug(
            "generate_analysis_dialog_confirm_clicked",
            run_id=self._run.run_id,
            provider_id=provider_id,
            model_name=model_name,
        )
        dispatched = self._dispatcher.regenerate_analysis(self._run.run_id, provider_id, model_name)
        if dispatched:
            self._enter_generating_state()
        else:
            self._enter_gate_busy_state()

    def _enter_generating_state(self) -> None:
        logger.debug("generate_analysis_dialog_generating", run_id=self._run.run_id)
        self._fields_container.setVisible(False)
        self._busy_label.setVisible(False)
        self._progress_label.setText("Waiting for response — 0.0 s")
        self._progress_label.setVisible(True)
        self._confirm_button.setEnabled(False)

    def _enter_gate_busy_state(self) -> None:
        logger.debug("generate_analysis_dialog_gate_busy", run_id=self._run.run_id)
        self._busy_label.setVisible(True)
        self._confirm_button.setEnabled(False)
        self._confirm_button.setToolTip(_GATE_BUSY_TOOLTIP)

    def _on_inference_activity_changed(self, payload: object) -> None:
        if not isinstance(payload, InferenceActivityChangedEvent):
            return
        if payload.state.current is not InferenceActivity.IDLE:
            return
        if self._busy_label.isVisible():
            logger.debug("generate_analysis_dialog_gate_idle", run_id=self._run.run_id)
            self._busy_label.setVisible(False)
            self._confirm_button.setEnabled(True)
            self._confirm_button.setToolTip("")
            return
        if self._progress_label.isVisible():
            # The gate the analysis call held has been released -- the call has
            # settled (success or failure); the Run Analysis tab renders the outcome.
            self._close_settled()

    def _on_inference_progress(self, payload: object) -> None:
        if not isinstance(payload, InferenceProgressEvent):
            return
        if (
            payload.context is not InferenceContext.RUN_ANALYSIS
            or payload.run_id != self._run.run_id
        ):
            return
        elapsed_s = payload.elapsed_ms / 1000
        if not payload.first_token_received:
            self._progress_label.setText(f"Waiting for response — {elapsed_s:.1f} s")
            return
        prefix = "~" if payload.tokens_estimated else ""
        tokens = payload.tokens_received or 0
        self._progress_label.setText(
            f"Receiving — {prefix}{tokens} tokens · {elapsed_s:.1f} s elapsed"
        )

    def _on_run_analysis_received(self, payload: object) -> None:
        if not isinstance(payload, RunAnalysisReceivedEvent):
            return
        if payload.run_id != self._run.run_id:
            return
        self._close_settled()

    def _close_settled(self) -> None:
        if self._settled:
            return
        self._settled = True
        self._gate_subscription.cancel()
        self._progress_subscription.cancel()
        self._analysis_subscription.cancel()
        self.accept()


class _SetProvider(Protocol):
    """Structural view of the model-dropdown widget's public ``set_provider`` method."""

    def set_provider(self, provider_id: str) -> None: ...
