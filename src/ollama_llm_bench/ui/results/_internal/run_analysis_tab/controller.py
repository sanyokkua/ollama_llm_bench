"""``JudgeAnalysisTabController`` -- the Run Analysis tab's sub-controller (STORY-065).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/run_analysis_tab.md``
§4 (generation timing), §5 (metadata line), §7-§8 (toolbar, Generate/Regenerate flow),
§9 (empty/generating/failed states), §11 (live update), §13 (event-bus integration);
``07_Common_Dialogs/generate_analysis_dialog.md`` §8 (confirm behaviour). Depends only
on ``ResultGateway``, the ``EventBus``, and ``Clipboard`` (D-R-06; no
``PerRunViewStateStore`` -- this tab holds no persisted view state of its own, §12).

Also implements ``regenerate_analysis(run_id, provider_id, model_name) -> bool``,
structurally satisfying ``ui.common_dialogs.protocols.RunAnalysisDispatcher`` -- the
Generate Analysis dialog's entry point back into this controller (generate_analysis_dialog.md
§8 step 1).

No persisted column exists for the narrative's generation timestamp/duration
(``BenchmarkRun``/``RunStatusPatch`` carry no such field -- see STORY-065's Notes).
This controller therefore keeps a **session-only** ``JudgeAnalysisSessionState`` per
``run_id``: populated when a generation completes this session, lost on a tab reopen
or app restart (the narrative body itself is always rebuilt from the persisted
``run_analysis`` field, per §12).
"""

from datetime import UTC, datetime
import time
from typing import TYPE_CHECKING, Protocol

import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    InferenceActivityState,
    ModelName,
    ProviderId,
    ResultStatus,
    RunId,
    RunStatusPatch,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    SIGNAL_RUN_ANALYSIS_RECEIVED,
    EventBus,
    InferenceActivityChangedEvent,
    RunAnalysisReceivedEvent,
)
from ollama_llm_bench.ui.results._internal.run_analysis_tab import select
from ollama_llm_bench.ui.results._internal.run_analysis_tab.select import JudgeAnalysisSessionState
from ollama_llm_bench.ui.results.models import JudgeAnalysisViewModel
from ollama_llm_bench.ui.results.protocols import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
    ResultGateway,
)

if TYPE_CHECKING:
    # Only for the type annotation on `_view` -- view.py imports this module for
    # JudgeAnalysisTabView's controller reference, so a real module-level import here
    # would be a runtime import cycle (mirrors ui/results/_internal/summary_tab/controller.py).
    from ollama_llm_bench.ui.results._internal.run_analysis_tab.view import JudgeAnalysisTabView

__all__: list[str] = ["JudgeAnalysisTabController"]

logger = structlog.get_logger(__name__)


class _ViewProtocol(Protocol):
    """The subset of ``JudgeAnalysisTabView``'s surface this controller drives."""

    def apply(self, view_model: JudgeAnalysisViewModel) -> None: ...


def _format_model_display(*, provider_name: str | None, model_name: ModelName) -> str:
    """Render the metadata line's "model" segment from a **display name** only.

    ``run_analysis_tab.md`` §5 and the app-wide rule in ``CLAUDE.md`` both forbid
    ever rendering the internal ``provider_id`` (a UUID4 in production) to the
    user. ``provider_name`` is populated by the concrete ``ResultGateway`` adapter
    (the only layer with ``ProviderRegistry`` access) on the completed
    ``JudgeAnalysisGenerationResult``; it is absent only when the adapter has not
    yet been wired (STORY-065's Notes) or a fake test double omits it, in which
    case the model name alone is shown -- never a fallback to any id.

    Args:
        provider_name: The analysis provider's snapshot display name, or ``None``.
        model_name: The analysis model's name.

    Returns:
        ``"<provider_name> / <model_name>"`` when a provider name is available,
        otherwise just ``model_name``.
    """
    if provider_name:
        return f"{provider_name} / {model_name}"
    return model_name


class JudgeAnalysisTabController:
    """Owns the Run Analysis tab's session-only generation state; derives the
    ``JudgeAnalysisViewModel`` and pushes it to the bound ``JudgeAnalysisTabView``."""

    def __init__(self, *, gateway: ResultGateway, bus: EventBus, clipboard: Clipboard) -> None:
        self._gateway = gateway
        self._bus = bus
        self._clipboard = clipboard
        self._run_id: RunId | None = None
        self._is_terminal = True
        self._gate_state = InferenceActivityState(current=InferenceActivity.IDLE)
        self._session_by_run: dict[RunId, JudgeAnalysisSessionState] = {}
        self._dispatched_at: dict[RunId, float] = {}
        self._dispatched_model_name: dict[RunId, ModelName] = {}
        self._view: _ViewProtocol | None = None
        logger.debug("run_analysis_tab_controller_constructed")

    def bind(self, view: "JudgeAnalysisTabView") -> None:
        """Subscribe to ``_run_analysis_received``/``_inference_activity_changed``,
        owner-bound to ``view``'s lifetime."""
        self._view = view
        self._bus.subscribe(
            SIGNAL_RUN_ANALYSIS_RECEIVED, self._on_run_analysis_received, owner=view
        )
        self._bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED, self._on_inference_activity_changed, owner=view
        )
        logger.debug("run_analysis_tab_controller_bound")

    def set_run_context(self, *, run_id: RunId | None) -> None:
        """Re-load the run's narrative on a run-selection change (§13)."""
        logger.debug("run_analysis_tab_run_context_set", run_id=run_id)
        self._run_id = run_id
        self.recompute_and_push()

    def set_run_terminal_state(self, *, is_terminal: bool) -> None:
        """Enable/disable the Generate/Regenerate button as runs enter/leave a
        non-terminal state, application-wide (§7, the view-only-during-run rule)."""
        self._is_terminal = is_terminal
        self.recompute_and_push()

    def recompute_and_push(self) -> None:
        """Re-derive the ``JudgeAnalysisViewModel`` and push it to the view."""
        if self._view is None:
            return
        run = self._gateway.get_run(self._run_id) if self._run_id is not None else None
        has_completed = (
            self._has_completed_results(self._run_id) if self._run_id is not None else False
        )
        session = (
            self._session_by_run.get(self._run_id, JudgeAnalysisSessionState())
            if self._run_id is not None
            else JudgeAnalysisSessionState()
        )
        view_model = select.select_judge_analysis_view_model(
            run=run,
            has_completed_results=has_completed,
            is_terminal=self._is_terminal,
            gate_state=self._gate_state,
            session=session,
        )
        self._view.apply(view_model)

    def on_copy_clicked(self) -> None:
        """Copy the currently displayed narrative's Markdown source (§7)."""
        if self._run_id is None:
            return
        run = self._gateway.get_run(self._run_id)
        if run.run_analysis is None:
            return
        logger.debug("run_analysis_tab_copy_clicked", run_id=self._run_id)
        self._clipboard.copy_text(run.run_analysis)

    def regenerate_analysis(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> bool:
        """Structurally satisfies ``ui.common_dialogs.protocols.RunAnalysisDispatcher``.

        Dispatches through the Gateway (generate_analysis_dialog.md §8 step 1);
        returns ``True`` when the single-inference gate was acquired and the call was
        enqueued, ``False`` when the gate is already held by another activity
        (STORY-065-AC-5/AC-6).
        """
        logger.debug(
            "run_analysis_tab_regenerate_analysis_requested",
            run_id=run_id,
            provider_id=provider_id,
            model_name=model_name,
        )
        self._dispatched_at[run_id] = time.monotonic()
        self._dispatched_model_name[run_id] = model_name
        dispatched = self._gateway.regenerate_run_analysis(
            run_id,
            provider_id,
            model_name,
            on_complete=lambda result: self._on_regeneration_complete(run_id, result),
        )
        if not dispatched:
            self._dispatched_at.pop(run_id, None)
            self._dispatched_model_name.pop(run_id, None)
        return dispatched

    def _on_regeneration_complete(
        self, run_id: RunId, result: JudgeAnalysisGenerationResult
    ) -> None:
        logger.debug(
            "run_analysis_tab_regeneration_complete", run_id=run_id, outcome=result.outcome.value
        )
        started_at = self._dispatched_at.pop(run_id, None)
        model_name = self._dispatched_model_name.pop(run_id, "")
        if (
            result.outcome is JudgeAnalysisGenerationOutcome.GENERATED
            and result.run_analysis_markdown
        ):
            self._apply_generated(
                run_id=run_id,
                started_at=started_at,
                model_display=_format_model_display(
                    provider_name=result.provider_name, model_name=model_name
                ),
                markdown=result.run_analysis_markdown,
                is_regeneration=result.is_regeneration,
            )
        elif result.outcome is JudgeAnalysisGenerationOutcome.FAILED:
            self._session_by_run[run_id] = JudgeAnalysisSessionState(
                metadata_line=self._session_by_run.get(
                    run_id, JudgeAnalysisSessionState()
                ).metadata_line,
                error_banner=result.error_message or "The analysis model could not be reached.",
            )
        if self._run_id == run_id:
            self.recompute_and_push()

    def _apply_generated(
        self,
        *,
        run_id: RunId,
        started_at: float | None,
        model_display: str,
        markdown: str,
        is_regeneration: bool,
    ) -> None:
        self._gateway.persist_run_analysis(run_id, RunStatusPatch(run_analysis=markdown))
        duration_s = (time.monotonic() - started_at) if started_at is not None else 0.0
        generated_at_display = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        self._session_by_run[run_id] = JudgeAnalysisSessionState(
            metadata_line=select.format_metadata_line(
                generated_at_display=generated_at_display,
                duration_s=duration_s,
                model_display=model_display,
            ),
            error_banner=None,
        )
        run_mode = self._gateway.get_run(run_id).run_mode
        self._bus.emit(
            SIGNAL_RUN_ANALYSIS_RECEIVED,
            RunAnalysisReceivedEvent(
                run_id=run_id,
                run_mode=run_mode,
                analysis_markdown=markdown,
                generated_at=datetime.now(UTC).isoformat(),
                is_regeneration=is_regeneration,
            ),
        )

    def _on_run_analysis_received(self, payload: object) -> None:
        if not isinstance(payload, RunAnalysisReceivedEvent):
            return
        logger.debug(
            "run_analysis_tab_event_received",
            signal_name="run_analysis_received",
            run_id=payload.run_id,
        )
        if payload.run_id == self._run_id:
            self.recompute_and_push()

    def _on_inference_activity_changed(self, payload: object) -> None:
        if not isinstance(payload, InferenceActivityChangedEvent):
            return
        logger.debug("run_analysis_tab_event_received", signal_name="inference_activity_changed")
        self._gate_state = payload.state
        self.recompute_and_push()

    def _has_completed_results(self, run_id: RunId) -> bool:
        return any(
            result.status is ResultStatus.COMPLETED for result in self._gateway.list_results(run_id)
        )
