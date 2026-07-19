"""``CountersController`` -- counters, stage bar, per-stage badges, ETA, and model
identification (``04_Progress_Widget/implementation_structure.md`` §4.1; description.md
§4, §5, §6.1; STORY-058-AC-4, STORY-058-AC-5).

Depends only on ``ProgressGateway`` plus ``EventBus`` (D-R-06) -- never a raw backend
Store/Service Protocol, and never ``AdaptiveTimeoutService``/the circuit breaker.
"""

import msgspec
from PySide6.QtCore import QTimer
import structlog

from ollama_llm_bench.backend.domain import RunId, RunMode
from ollama_llm_bench.backend.events import (
    SIGNAL_PROGRESS_UPDATED,
    SIGNAL_RUN_STARTED,
    SIGNAL_STAGE_CHANGED,
    EventBus,
    ProgressUpdatedEvent,
    RunStartedEvent,
    StageChangedEvent,
)
from ollama_llm_bench.ui.progress._internal.select import (
    _CountersInputs,
    estimate_eta_label,
    format_duration_ms,
    parse_stage,
    select_counters,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import CountersViewModel, RunStage
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = ["CountersController"]

logger = structlog.get_logger(__name__)

_EMPTY_COUNTERS_VM = CountersViewModel(
    stage=RunStage.INITIALIZING,
    tasks_done=0,
    tasks_total=0,
    eta_label="—",
    total_time_label="—",
    counts_by_status={},
    bar_segments=(),
    badge_counts=(),
    judge_phase_active=False,
    provider_label="—",
    model_label="—",
)


class CountersController:
    """Subscribes ``_progress_updated``/``_stage_changed``/``_run_started``; coalesces
    consecutive ``_progress_updated`` bursts to one repaint per event-loop turn."""

    def __init__(self, *, gateway: ProgressGateway, event_bus: EventBus) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._view: ProgressView | None = None
        self._run_id: RunId | None = None
        self._stage = RunStage.INITIALIZING
        self._last_live_stage: RunStage | None = None
        self._judge_phase_active = False
        self._latest_payload: ProgressUpdatedEvent | None = None
        self._flush_scheduled = False
        logger.debug("counters_controller_constructed")

    def bind(self, view: ProgressView) -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime."""
        self._view = view
        self._event_bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_started, owner=view)
        self._event_bus.subscribe(SIGNAL_STAGE_CHANGED, self._on_stage_changed, owner=view)
        self._event_bus.subscribe(SIGNAL_PROGRESS_UPDATED, self._on_progress_updated, owner=view)

    def _on_run_started(self, payload: object) -> None:
        if not isinstance(payload, RunStartedEvent):
            return
        logger.debug("counters_event_received", signal_name=SIGNAL_RUN_STARTED)
        self._run_id = payload.run_id
        self._stage = RunStage.INITIALIZING
        self._judge_phase_active = payload.run_mode == RunMode.GRADED
        self._latest_payload = None
        self._apply(_EMPTY_COUNTERS_VM)

    def _on_stage_changed(self, payload: object) -> None:
        if not isinstance(payload, StageChangedEvent):
            return
        logger.debug(
            "counters_event_received", signal_name=SIGNAL_STAGE_CHANGED, stage=payload.stage
        )
        self._stage = parse_stage(payload.stage)
        self._last_live_stage = self._stage
        if self._latest_payload is not None:
            self._flush()

    def set_stage(self, stage: RunStage) -> None:
        """Force-set the badge stage to a terminal/paused value the pipeline never
        emits via ``_stage_changed`` (state_machine.md §1, §4; description.md §3.1).

        Called by ``ProgressController`` on ``_run_paused``/``_run_stopped``/
        ``_run_finished``/``_run_failed`` and on SPEC-098 reconciliation --
        those events reach ``ProgressController`` only, so it must push the
        matching stage here itself; the pipeline never emits a
        ``_stage_changed`` for a terminal/paused stage (STORY-058 defect fix).
        """
        logger.debug("counters_stage_forced", stage=stage.value)
        self._stage = stage
        self._render_current_stage()

    def resume_live_stage(self) -> None:
        """Restore the badge to the last-known live pipeline stage on
        ``_run_resumed``, or ``RunStage.INITIALIZING`` if no live stage has been
        observed yet (state_machine.md §1; STORY-058 defect fix)."""
        self.set_stage(self._last_live_stage or RunStage.INITIALIZING)

    def _render_current_stage(self) -> None:
        if self._latest_payload is not None:
            self._flush()
            return
        self._apply(msgspec.structs.replace(_EMPTY_COUNTERS_VM, stage=self._stage))

    def _on_progress_updated(self, payload: object) -> None:
        if not isinstance(payload, ProgressUpdatedEvent):
            return
        logger.debug("counters_event_received", signal_name=SIGNAL_PROGRESS_UPDATED)
        self._latest_payload = payload
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        QTimer.singleShot(0, self._flush)

    def _flush(self) -> None:
        self._flush_scheduled = False
        payload = self._latest_payload
        if payload is None:
            return
        eta_label, total_time_label = self._time_labels(payload)
        vm = select_counters(
            payload=payload,
            inputs=_CountersInputs(
                stage=self._stage,
                judge_phase_active=self._judge_phase_active,
                eta_label=eta_label,
                total_time_label=total_time_label,
                provider_label=str(payload.current_provider_id or "—"),
                model_label=str(payload.current_model_name or "—"),
            ),
        )
        logger.debug("counters_applied", tasks_done=vm.tasks_done, tasks_total=vm.tasks_total)
        self._apply(vm)

    def _time_labels(self, payload: ProgressUpdatedEvent) -> tuple[str, str]:
        if self._run_id is None:
            return "—", "—"
        header = self._gateway.run_header(self._run_id)
        total_time_label = format_duration_ms(header.total_elapsed_ms)
        remaining = max(payload.total_count - payload.completed_count, 0)
        eta_label = estimate_eta_label(
            elapsed_ms=header.total_elapsed_ms,
            completed=payload.completed_count,
            remaining=remaining,
        )
        return eta_label, total_time_label

    def _apply(self, vm: CountersViewModel) -> None:
        if self._view is not None:
            self._view.apply_counters(vm)
