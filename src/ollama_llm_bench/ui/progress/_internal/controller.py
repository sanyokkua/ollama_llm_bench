"""``ProgressController`` -- thin parent router: owns the sub-controllers, applies
``state_machine.md`` transitions, and forwards header run-control clicks
(``04_Progress_Widget/implementation_structure.md`` §3; ``state_machine.md``;
SPEC-098; STORY-058-AC-2, STORY-058-AC-3, EC-RUN-2).

The parent holds no business logic: it owns each subscription, tracks the top-level
widget state, and routes Pause/Resume/Stop/rename clicks to ``ProgressGateway``. The
SPEC-098 bounded reconciliation timer follows
``ui/main_window/_internal/close_handler.py``'s "first callback wins" `QTimer` vs
`EventBus` race pattern: a `_settled` guard flag lets whichever side (the terminal
event or the timeout) fires first stop the other.
"""

from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QTimer
import structlog

from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_PAUSED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_RESUMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    EventBus,
    RunFailedEvent,
    RunFinishedEvent,
    RunIdChangedEvent,
    RunPausedEvent,
    RunRenamedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStoppedEvent,
)
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.ui.progress._internal.counters_controller import CountersController
from ollama_llm_bench.ui.progress._internal.select import (
    select_header,
    terminal_stage_for_run_status,
)
from ollama_llm_bench.ui.progress._internal.stability_controller import StabilityController
from ollama_llm_bench.ui.progress._internal.stop_confirmation import confirm_stop
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import RunStage
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

if TYPE_CHECKING:
    from ollama_llm_bench.backend.domain import RunId

__all__: list[str] = ["ProgressController"]

logger = structlog.get_logger(__name__)

# state_machine.md §1/§2's top-level widget states this controller tracks. "Pausing"
# (description.md §3.4) is a transient draining condition, not its own tracked state --
# the widget_state stays "Running" while draining a Pause (Stop must stay available).
STATE_EMPTY = "Empty"
STATE_INITIALIZING = "Initializing"
STATE_RUNNING = "Running"
STATE_PAUSED = "Paused"
STATE_STOPPING = "Stopping"
STATE_VIEWING_PAST_RUN = "ViewingPastRun"

_DEFAULT_RECONCILE_TIMEOUT_MS = 5000

# description.md §3.4's exact draining-sub-state status-line text -- shown while a
# Pause/Stop request is in flight, between the user's click and the terminal event.
_PAUSING_STATUS_TEXT = "Pausing — finishing the current call…"
_STOPPING_STATUS_TEXT = "Stopping — cancelling the current call…"

type _DrainingIntent = Literal["pause", "stop"]


class ProgressController:
    """Thin parent: state machine, run-control wiring, owns the two STORY-058
    sub-controllers (``CountersController``, ``StabilityController``)."""

    def __init__(
        self,
        *,
        gateway: ProgressGateway,
        event_bus: EventBus,
        log_formatter: LogFormatter | None = None,
        reconcile_timeout_ms: int = _DEFAULT_RECONCILE_TIMEOUT_MS,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        # Retained collaborator for STORY-059/STORY-060's Current-Task/Log regions;
        # this story's own code paths do not call it (no Log region built yet).
        self._log_formatter = log_formatter
        self._reconcile_timeout_ms = reconcile_timeout_ms
        self._view: ProgressView | None = None
        self._state = STATE_EMPTY
        self._run_id: RunId | None = None
        self._run_name = ""
        self._settled = True
        self._reconcile_timer: QTimer | None = None
        self._draining_intent: _DrainingIntent | None = None
        self.counters = CountersController(gateway=gateway, event_bus=event_bus)
        self.stability = StabilityController(gateway=gateway, event_bus=event_bus)
        logger.debug("progress_controller_constructed")

    def bind(self, view: ProgressView) -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime; wire clicks."""
        self._view = view
        self.counters.bind(view)
        self.stability.bind(view)
        bus = self._event_bus
        bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_started, owner=view)
        bus.subscribe(SIGNAL_RUN_PAUSED, self._on_run_paused, owner=view)
        bus.subscribe(SIGNAL_RUN_RESUMED, self._on_run_resumed, owner=view)
        bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_stopped, owner=view)
        bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_finished, owner=view)
        bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_failed, owner=view)
        bus.subscribe(SIGNAL_RUN_RENAMED, self._on_run_renamed, owner=view)
        bus.subscribe(SIGNAL_RUN_ID_CHANGED, self._on_run_id_changed, owner=view)
        view.rename_clicked.connect(self._on_rename_clicked)
        view.pause_resume_clicked.connect(self._on_pause_resume_clicked)
        view.stop_clicked.connect(self._on_stop_clicked)
        view.retry_probe_clicked.connect(self.stability.on_retry_probe_clicked)
        self._push_header()

    # -- Event Bus handlers ---------------------------------------------------

    def _on_run_started(self, payload: object) -> None:
        if not isinstance(payload, RunStartedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_STARTED)
        self._run_id = payload.run_id
        self._run_name = payload.run_name
        self._transition(STATE_INITIALIZING)

    def _on_run_paused(self, payload: object) -> None:
        if not isinstance(payload, RunPausedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_PAUSED)
        self._settle_reconciliation()
        self._transition(STATE_PAUSED)
        self.counters.set_stage(RunStage.PAUSED)

    def _on_run_resumed(self, payload: object) -> None:
        if not isinstance(payload, RunResumedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_RESUMED)
        self._transition(STATE_RUNNING)
        self.counters.resume_live_stage()

    def _on_run_stopped(self, payload: object) -> None:
        if not isinstance(payload, RunStoppedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_STOPPED)
        self._settle_reconciliation()
        self._transition(STATE_VIEWING_PAST_RUN)
        self.counters.set_stage(RunStage.STOPPED)

    def _on_run_finished(self, payload: object) -> None:
        if not isinstance(payload, RunFinishedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_FINISHED)
        self._settle_reconciliation()
        self._transition(STATE_VIEWING_PAST_RUN)
        self.counters.set_stage(terminal_stage_for_run_status(payload.run_status))

    def _on_run_failed(self, payload: object) -> None:
        if not isinstance(payload, RunFailedEvent):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_FAILED)
        self._settle_reconciliation()
        self._transition(STATE_VIEWING_PAST_RUN)
        self.counters.set_stage(RunStage.FAILED)

    def _on_run_renamed(self, payload: object) -> None:
        if not isinstance(payload, RunRenamedEvent):
            return
        if payload.run_id != self._run_id:
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_RENAMED)
        self._run_name = payload.new_name
        self._push_header()

    def _on_run_id_changed(self, payload: object) -> None:
        if not isinstance(payload, RunIdChangedEvent):
            return
        if self._state not in (STATE_EMPTY, STATE_VIEWING_PAST_RUN):
            return
        logger.debug("progress_event_received", signal_name=SIGNAL_RUN_ID_CHANGED)
        if payload.run_id is None:
            self._run_id = None
            self._run_name = ""
            self._transition(STATE_EMPTY)
            return
        self._run_id = payload.run_id
        run = self._gateway.run_header(payload.run_id)
        self._run_name = run.run_name or ""
        self._transition(STATE_VIEWING_PAST_RUN)

    # -- User-triggered actions ------------------------------------------------

    def _on_rename_clicked(self) -> None:
        from ollama_llm_bench.ui.common_dialogs import make_rename_run_dialog  # noqa: PLC0415

        if self._view is None or self._run_id is None:
            return
        logger.debug("progress_rename_clicked", run_id=self._run_id)
        run = self._gateway.run_metadata(self._run_id)
        dialog = make_rename_run_dialog(
            gateway=self._gateway,
            run_id=self._run_id,
            current_custom_name=run.run_name,
            computed_default_name=run.run_name or "",
            parent=self._view,
        )
        dialog.exec()

    def _on_pause_resume_clicked(self) -> None:
        if self._state == STATE_PAUSED:
            logger.debug("progress_resume_clicked", run_id=self._run_id)
            self._gateway.resume_run()
            return
        logger.debug("progress_pause_clicked", run_id=self._run_id)
        self._gateway.pause_run()
        self._begin_draining(intent="pause", status_text=_PAUSING_STATUS_TEXT)

    def _on_stop_clicked(self) -> None:
        if self._view is None:
            return
        logger.debug("progress_stop_clicked", run_id=self._run_id)
        if not confirm_stop(parent=self._view):
            logger.debug("progress_stop_declined", run_id=self._run_id)
            return
        logger.debug("progress_stop_confirmed", run_id=self._run_id)
        self._gateway.stop_run()
        self._transition(STATE_STOPPING)
        self._begin_draining(intent="stop", status_text=_STOPPING_STATUS_TEXT)

    # -- State machine ----------------------------------------------------------

    def _transition(self, state: str) -> None:
        logger.debug("progress_state_transition", from_state=self._state, to_state=state)
        self._state = state
        self._push_header()

    def _push_header(self) -> None:
        if self._view is None:
            return
        affordances = select_header(widget_state=self._state)
        self._view.apply_header(run_name=self._run_name, affordances=affordances)

    # -- SPEC-098 bounded reconciliation timer ----------------------------------

    def _begin_draining(self, *, intent: _DrainingIntent, status_text: str) -> None:
        self._settled = False
        self._draining_intent = intent
        if self._view is not None:
            self._view.apply_draining_status(status_text)
        # Parented to `self._view` (never a bare `QTimer()`): a controller is not a
        # QObject, so an unparented timer plus its `timeout` connection back to
        # `self` forms a reference cycle that only the cyclic GC reclaims -- not
        # deterministically at view-teardown time. Parenting ties the timer's
        # lifetime to the view's, so it is destroyed the moment the view is.
        timer = QTimer(self._view)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_reconcile_timeout)
        timer.start(self._reconcile_timeout_ms)
        self._reconcile_timer = timer

    def _settle_reconciliation(self) -> None:
        if self._settled:
            return
        self._settled = True
        self._draining_intent = None
        self._clear_draining_status()
        if self._reconcile_timer is not None:
            self._reconcile_timer.stop()
            self._reconcile_timer = None

    def _clear_draining_status(self) -> None:
        if self._view is not None:
            self._view.apply_draining_status(None)

    def _on_reconcile_timeout(self) -> None:
        if self._settled:
            return
        self._settled = True
        self._reconcile_timer = None
        intent = self._draining_intent
        self._draining_intent = None
        self._clear_draining_status()
        still_active = self._run_id is not None and self._gateway.is_run_active()
        run_status = (
            self._gateway.run_header(self._run_id).status if self._run_id is not None else None
        )
        logger.debug(
            "progress_reconciliation_timeout",
            run_id=self._run_id,
            still_active=still_active,
            run_status=run_status,
            intent=intent,
        )
        if still_active:
            # SPEC-098: `is_run_active()` reports `True` for both the genuinely
            # running and the parked-paused in-memory states (there is no
            # persisted PAUSED status to disambiguate). A lost `_run_paused`
            # event during a Pause drain most plausibly settled to Paused; a
            # Stop drain that is somehow still active has no better fallback
            # than treating the run as still Running.
            if intent == "pause":
                self._transition(STATE_PAUSED)
                self.counters.set_stage(RunStage.PAUSED)
            else:
                self._transition(STATE_RUNNING)
            return
        self._transition(STATE_VIEWING_PAST_RUN)
        if run_status is not None:
            self.counters.set_stage(terminal_stage_for_run_status(run_status))
