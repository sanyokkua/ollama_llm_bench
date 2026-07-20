"""CurrentTaskController -- the Current-task grid and the Inference/Judge live
progress sub-rows (04_Progress_Widget/implementation_structure.md §4.2;
description.md §7, §7.1; STORY-059-AC-1..6; EC-RUN-17, EC-RUN-18, EC-RUN-19,
EC-RUN-23, EC-PROV-1).

Depends only on ProgressGateway plus EventBus (D-R-06) -- this sub-controller
calls no ProgressGateway method at all (confirmed by the story's own spec-clause
annotation for 08-E §7b.4); gateway is accepted only for construction-signature
symmetry with its sibling sub-controllers.

There is at most one active task in flight at a time (serial execution, D-R-16), so
the EC-RUN-23 out-of-order-judge-progress guard is a single boolean
(_judge_phase_active), not a per-result_id comparison.
"""

import structlog

from ollama_llm_bench.backend.domain import ErrorKind, InferenceContext
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_PROGRESS,
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_JUDGE_COMPLETED,
    SIGNAL_JUDGE_STARTED,
    SIGNAL_TASK_COMPLETED,
    SIGNAL_TASK_RETRY,
    EventBus,
    InferenceProgressEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.ui.progress._internal.select import (
    INFERENCE_COMPLETE_PLACEHOLDER,
    accepts_progress_context,
    format_duration_ms,
    format_inference_generating_label,
    format_inference_waiting_label,
    format_judge_receiving_label,
    format_judge_waiting_label,
    format_retry_label,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import CurrentTaskViewModel
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = ["CurrentTaskController"]

logger = structlog.get_logger(__name__)


class CurrentTaskController:
    """Subscribes _inference_started/_inference_progress/_judge_started/
    _judge_completed/_task_completed/_task_retry; derives CurrentTaskViewModel."""

    def __init__(self, *, gateway: ProgressGateway, event_bus: EventBus) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._view: ProgressView | None = None
        self._task_id: str | None = None
        self._task_time_label = "—"
        self._timeouts = 0
        self._retry_active = False
        self._retry_label: str | None = None
        self._inference_visible = False
        self._inference_label: str | None = None
        self._judge_visible = False
        self._judge_label: str | None = None
        self._judge_phase_active = False
        logger.debug("current_task_controller_constructed")

    def bind(self, view: ProgressView) -> None:
        """Subscribe to the Event Bus, owner-bound to view's lifetime."""
        self._view = view
        bus = self._event_bus
        bus.subscribe(SIGNAL_INFERENCE_STARTED, self._on_inference_started, owner=view)
        bus.subscribe(SIGNAL_INFERENCE_PROGRESS, self._on_inference_progress, owner=view)
        bus.subscribe(SIGNAL_JUDGE_STARTED, self._on_judge_started, owner=view)
        bus.subscribe(SIGNAL_JUDGE_COMPLETED, self._on_judge_completed, owner=view)
        bus.subscribe(SIGNAL_TASK_COMPLETED, self._on_task_completed, owner=view)
        bus.subscribe(SIGNAL_TASK_RETRY, self._on_task_retry, owner=view)

    def _on_inference_started(self, payload: object) -> None:
        if not isinstance(payload, InferenceStartedEvent):
            return
        logger.debug("current_task_event_received", signal_name=SIGNAL_INFERENCE_STARTED)
        self._task_id = payload.task_id
        self._timeouts = 0
        self._retry_active = False
        self._retry_label = None
        self._judge_phase_active = False
        self._judge_visible = False
        self._judge_label = None
        self._inference_visible = True
        self._inference_label = format_inference_waiting_label(0)
        self._task_time_label = "0s"
        self._apply()

    def _on_inference_progress(self, payload: object) -> None:
        if not isinstance(payload, InferenceProgressEvent):
            return
        if not accepts_progress_context(payload.context):
            return
        logger.debug(
            "current_task_event_received",
            signal_name=SIGNAL_INFERENCE_PROGRESS,
            context=payload.context.value,
        )
        if payload.context == InferenceContext.BENCHMARK_JUDGE:
            self._apply_judge_progress(payload)
            return
        self._apply_inference_progress(payload)

    def _apply_inference_progress(self, payload: InferenceProgressEvent) -> None:
        self._task_time_label = format_duration_ms(payload.elapsed_ms)
        if payload.first_token_received and payload.tokens_received is not None:
            self._inference_label = format_inference_generating_label(
                tokens=payload.tokens_received,
                elapsed_ms=payload.elapsed_ms,
                is_estimate=payload.tokens_estimated,
            )
        else:
            self._inference_label = format_inference_waiting_label(payload.elapsed_ms)
        self._apply()

    def _apply_judge_progress(self, payload: InferenceProgressEvent) -> None:
        if not self._judge_phase_active:
            logger.warning(
                "current_task_out_of_order_judge_progress_ignored", result_id=payload.result_id
            )
            return
        self._task_time_label = format_duration_ms(payload.elapsed_ms)
        if payload.first_token_received and payload.tokens_received is not None:
            self._judge_label = format_judge_receiving_label(
                tokens=payload.tokens_received,
                elapsed_ms=payload.elapsed_ms,
                is_estimate=payload.tokens_estimated,
            )
        else:
            self._judge_label = format_judge_waiting_label(payload.elapsed_ms)
        self._apply()

    def _on_judge_started(self, payload: object) -> None:
        if not isinstance(payload, JudgeStartedEvent):
            return
        logger.debug("current_task_event_received", signal_name=SIGNAL_JUDGE_STARTED)
        self._judge_phase_active = True
        self._judge_visible = True
        self._judge_label = format_judge_waiting_label(0)
        self._apply()

    def _on_judge_completed(self, payload: object) -> None:
        if not isinstance(payload, JudgeCompletedEvent):
            return
        logger.debug("current_task_event_received", signal_name=SIGNAL_JUDGE_COMPLETED)
        self._judge_visible = False
        self._judge_label = None
        self._judge_phase_active = False
        self._apply()

    def _on_task_completed(self, payload: object) -> None:
        if not isinstance(payload, TaskCompletedEvent):
            return
        logger.debug("current_task_event_received", signal_name=SIGNAL_TASK_COMPLETED)
        self._retry_active = False
        self._retry_label = None
        self._inference_visible = False
        self._inference_label = None
        self._judge_visible = False
        self._judge_label = None
        self._judge_phase_active = False
        self._apply()

    def _on_task_retry(self, payload: object) -> None:
        if not isinstance(payload, TaskRetryEvent):
            return
        logger.debug("current_task_event_received", signal_name=SIGNAL_TASK_RETRY)
        if payload.error_kind == ErrorKind.TIMEOUT:
            self._timeouts += 1
        self._retry_active = True
        self._retry_label = format_retry_label(
            attempt=payload.attempt,
            total_attempts=payload.total_attempts,
            reason=payload.reason,
        )
        self._apply()

    def _apply(self) -> None:
        inference_label = (
            INFERENCE_COMPLETE_PLACEHOLDER if self._judge_visible else self._inference_label
        )
        last_context: InferenceContext | None = None
        if self._judge_visible:
            last_context = InferenceContext.BENCHMARK_JUDGE
        elif self._inference_visible:
            last_context = InferenceContext.BENCHMARK_TASK
        stage_label = "judge" if self._judge_visible else (
            "inference" if self._inference_visible else "—"
        )
        vm = CurrentTaskViewModel(
            task_id=self._task_id,
            stage_label=stage_label,
            task_time_label=self._task_time_label,
            timeouts=self._timeouts,
            retry_active=self._retry_active,
            retry_label=self._retry_label,
            inference_progress_visible=self._inference_visible,
            inference_progress_label=inference_label,
            judge_progress_visible=self._judge_visible,
            judge_progress_label=self._judge_label,
            last_progress_context=last_context,
        )
        logger.debug("current_task_applied", task_id=vm.task_id, stage_label=vm.stage_label)
        if self._view is not None:
            self._view.apply_current_task(vm)

