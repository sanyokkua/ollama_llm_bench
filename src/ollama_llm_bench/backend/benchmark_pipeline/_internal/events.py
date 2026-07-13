"""Per-signal event-bus emission wrappers.

This module pairs signal-name constants to their payload Struct types, so a
caller passing the wrong payload type to the wrong wrapper is a mypy error, not
a runtime bug. Each wrapper is a thin, type-safe adapter that calls
``EventBus.emit`` with the matching ``SIGNAL_*`` constant and payload.
"""

from ollama_llm_bench.backend.events.models import (
    SIGNAL_INFERENCE_COMPLETED,
    SIGNAL_INFERENCE_PROGRESS,
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_JUDGE_COMPLETED,
    SIGNAL_JUDGE_STARTED,
    SIGNAL_PROGRESS_UPDATED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_PAUSED,
    SIGNAL_RUN_RESUMED,
    SIGNAL_RUN_START_FAILED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_STAGE_CHANGED,
    SIGNAL_TASK_COMPLETED,
    InferenceCompletedEvent,
    InferenceProgressEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    ProgressUpdatedEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStartFailedEvent,
    RunStoppedEvent,
    StageChangedEvent,
    TaskCompletedEvent,
)
from ollama_llm_bench.backend.events.protocols import EventBus

__all__: list[str] = [
    "emit_inference_completed",
    "emit_inference_progress",
    "emit_inference_started",
    "emit_judge_completed",
    "emit_judge_started",
    "emit_progress_updated",
    "emit_run_failed",
    "emit_run_finished",
    "emit_run_paused",
    "emit_run_resumed",
    "emit_run_start_failed",
    "emit_run_started",
    "emit_run_stopped",
    "emit_stage_changed",
    "emit_task_completed",
]


def emit_run_started(bus: EventBus, payload: RunStartedEvent) -> None:
    """Emit a run-started event when a benchmark run begins."""
    bus.emit(SIGNAL_RUN_STARTED, payload)


def emit_run_start_failed(bus: EventBus, payload: RunStartFailedEvent) -> None:
    """Emit a run-start-failed event when run creation fails before execution."""
    bus.emit(SIGNAL_RUN_START_FAILED, payload)


def emit_run_paused(bus: EventBus, payload: RunPausedEvent) -> None:
    """Emit a run-paused event when a running benchmark is paused."""
    bus.emit(SIGNAL_RUN_PAUSED, payload)


def emit_run_resumed(bus: EventBus, payload: RunResumedEvent) -> None:
    """Emit a run-resumed event when a paused benchmark resumes."""
    bus.emit(SIGNAL_RUN_RESUMED, payload)


def emit_run_stopped(bus: EventBus, payload: RunStoppedEvent) -> None:
    """Emit a run-stopped event when a benchmark is stopped by the user."""
    bus.emit(SIGNAL_RUN_STOPPED, payload)


def emit_run_finished(bus: EventBus, payload: RunFinishedEvent) -> None:
    """Emit a run-finished event when a benchmark completes normally."""
    bus.emit(SIGNAL_RUN_FINISHED, payload)


def emit_run_failed(bus: EventBus, payload: RunFailedEvent) -> None:
    """Emit a run-failed event when a fatal pipeline error halts the run."""
    bus.emit(SIGNAL_RUN_FAILED, payload)


def emit_stage_changed(bus: EventBus, payload: StageChangedEvent) -> None:
    """Emit a stage-changed event when the pipeline advances to a new phase."""
    bus.emit(SIGNAL_STAGE_CHANGED, payload)


def emit_progress_updated(bus: EventBus, payload: ProgressUpdatedEvent) -> None:
    """Emit a progress-updated event when aggregate run progress changes."""
    bus.emit(SIGNAL_PROGRESS_UPDATED, payload)


def emit_task_completed(bus: EventBus, payload: TaskCompletedEvent) -> None:
    """Emit a task-completed event when one task reaches terminal status."""
    bus.emit(SIGNAL_TASK_COMPLETED, payload)


def emit_inference_started(bus: EventBus, payload: InferenceStartedEvent) -> None:
    """Emit an inference-started event when an inference call begins."""
    bus.emit(SIGNAL_INFERENCE_STARTED, payload)


def emit_inference_progress(bus: EventBus, payload: InferenceProgressEvent) -> None:
    """Emit an inference-progress event as a heartbeat snapshot of in-flight LLM call."""
    bus.emit(SIGNAL_INFERENCE_PROGRESS, payload)


def emit_inference_completed(bus: EventBus, payload: InferenceCompletedEvent) -> None:
    """Emit an inference-completed event when an inference call finishes."""
    bus.emit(SIGNAL_INFERENCE_COMPLETED, payload)


def emit_judge_started(bus: EventBus, payload: JudgeStartedEvent) -> None:
    """Emit a judge-started event when the judge phase begins evaluating a task."""
    bus.emit(SIGNAL_JUDGE_STARTED, payload)


def emit_judge_completed(bus: EventBus, payload: JudgeCompletedEvent) -> None:
    """Emit a judge-completed event when the judge finishes evaluating a task."""
    bus.emit(SIGNAL_JUDGE_COMPLETED, payload)
