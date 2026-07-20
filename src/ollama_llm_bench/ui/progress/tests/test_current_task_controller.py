"""Colocated ``CurrentTaskController`` tests for ``ui/progress/`` (STORY-059)."""

from typing import TYPE_CHECKING

import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import ErrorKind, InferenceContext, ResultStatus, Verdict
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_PROGRESS,
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_JUDGE_COMPLETED,
    SIGNAL_JUDGE_STARTED,
    SIGNAL_TASK_COMPLETED,
    SIGNAL_TASK_RETRY,
    InferenceProgressEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.ui.progress._internal.current_task_controller import CurrentTaskController
from ollama_llm_bench.ui.progress._internal.select import (
    INFERENCE_COMPLETE_PLACEHOLDER,
    accepts_progress_context,
    format_inference_generating_label,
    format_inference_waiting_label,
    format_judge_receiving_label,
    format_judge_waiting_label,
    format_retry_label,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus

if TYPE_CHECKING:
    from ollama_llm_bench.ui.progress.models import CurrentTaskViewModel

_RUN_ID = 1
_RESULT_ID = 1
_TASK_ID = "task-1"
_PROVIDER_ID = "prov-1"
_MODEL_NAME = "model-1"


def _inference_started() -> InferenceStartedEvent:
    return InferenceStartedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        stage="inference",
        user_prompt="What is the capital of France?",
    )


def _inference_progress(
    *,
    context: InferenceContext,
    elapsed_ms: int,
    tokens_received: int | None,
    first_token_received: bool,
    tokens_estimated: bool = False,
) -> InferenceProgressEvent:
    return InferenceProgressEvent(
        context=context,
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        elapsed_ms=elapsed_ms,
        tokens_received=tokens_received,
        first_token_received=first_token_received,
        timestamp_ms=1_700_000_000_000,
        tokens_estimated=tokens_estimated,
    )


def _judge_started() -> JudgeStartedEvent:
    return JudgeStartedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        judge_provider_id=_PROVIDER_ID,
        judge_model_name="judge-model",
    )


def _judge_completed() -> JudgeCompletedEvent:
    return JudgeCompletedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        judge_verdict=Verdict.PASS,
        judge_reasoning="Correct answer.",
        judge_time_ms=500,
    )


def _task_completed() -> TaskCompletedEvent:
    return TaskCompletedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        result_status=ResultStatus.COMPLETED,
    )


def _task_retry(*, error_kind: ErrorKind = ErrorKind.PROVIDER) -> TaskRetryEvent:
    return TaskRetryEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        attempt=2,
        total_attempts=3,
        reason="Connection refused",
        error_kind=error_kind,
    )


def _bind(
    *, gateway: FakeProgressGateway, event_bus: FakeEventBus, qtbot: QtBot
) -> tuple[CurrentTaskController, ProgressView]:
    view = ProgressView()
    qtbot.addWidget(view)
    controller = CurrentTaskController(gateway=gateway, event_bus=event_bus)
    controller.bind(view)
    return controller, view


def test_inference_row_hidden_until_started_then_waiting(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-1

    Covers EC-RUN-18. Given no main inference is in flight, the Inference
    progress sub-row is hidden; given `_inference_started`, it is shown reset
    to sub-state A ("Waiting for first token — 0.0 s").
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    with structlog.testing.capture_logs() as logs:
        # Act
        fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())

    # Assert
    assert captured[-1].inference_progress_visible is True
    assert captured[-1].inference_progress_label == format_inference_waiting_label(0)
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_inference_row_transitions_to_generating(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-2

    Covers EC-RUN-19. Given sub-state A, a `_inference_progress` event with
    `context=BENCHMARK_TASK` and `first_token_received=True` transitions to
    sub-state B rendering tokens and elapsed seconds from the snapshot.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_INFERENCE_PROGRESS,
        _inference_progress(
            context=InferenceContext.BENCHMARK_TASK,
            elapsed_ms=5600,
            tokens_received=184,
            first_token_received=True,
        ),
    )

    # Assert
    vm = captured[-1]
    assert vm.inference_progress_visible is True
    assert vm.inference_progress_label == format_inference_generating_label(
        tokens=184, elapsed_ms=5600, is_estimate=False
    )


@pytest.mark.parametrize(
    ("context", "accepted"),
    [
        (InferenceContext.BENCHMARK_TASK, True),
        (InferenceContext.BENCHMARK_JUDGE, False),  # judge phase not started for this result yet
        (InferenceContext.RUN_ANALYSIS, False),
        (InferenceContext.PROVIDER_TEST, False),
    ],
)
def test_progress_context_filter(
    context: InferenceContext,
    accepted: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-059-AC-3

    Covers EC-RUN-23. Only BENCHMARK_TASK is accepted before `_judge_started`
    has fired for the active result; RUN_ANALYSIS/PROVIDER_TEST are never
    accepted at all (they belong to other widgets); the defensive
    BENCHMARK_JUDGE-before-`_judge_started` case is exercised directly by
    ``test_out_of_order_judge_progress_is_ignored`` below.
    """
    # Arrange
    assert accepts_progress_context(InferenceContext.BENCHMARK_TASK)
    assert accepts_progress_context(InferenceContext.BENCHMARK_JUDGE)
    assert not accepts_progress_context(InferenceContext.RUN_ANALYSIS)
    assert not accepts_progress_context(InferenceContext.PROVIDER_TEST)
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_INFERENCE_PROGRESS,
        _inference_progress(
            context=context, elapsed_ms=1000, tokens_received=10, first_token_received=True
        ),
    )

    # Assert
    if accepted and context == InferenceContext.BENCHMARK_TASK:
        assert captured[-1].inference_progress_label != format_inference_waiting_label(0)
    else:
        assert captured == []


def test_out_of_order_judge_progress_is_ignored(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-3

    Covers EC-RUN-23: a `context=BENCHMARK_JUDGE` progress event arriving
    before `_judge_started` for the active result is defensively ignored and
    logged as a warning, never rendered.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    with structlog.testing.capture_logs() as logs:
        # Act
        fake_event_bus.emit(
            SIGNAL_INFERENCE_PROGRESS,
            _inference_progress(
                context=InferenceContext.BENCHMARK_JUDGE,
                elapsed_ms=500,
                tokens_received=5,
                first_token_received=True,
            ),
        )

    # Assert
    assert captured == []
    assert any(
        entry["log_level"] == "warning"
        and entry["event"] == "current_task_out_of_order_judge_progress_ignored"
        for entry in logs
    )


def test_inference_placeholder_during_judge_phase(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-4

    Given the active result finished main inference and `_judge_started`
    fires, the Judge progress sub-row shows sub-state A and the Inference
    progress sub-row shows the "(complete — main inference finished)"
    placeholder rather than being hidden.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_JUDGE_STARTED, _judge_started())

    # Assert
    vm = captured[-1]
    assert vm.inference_progress_visible is True
    assert vm.inference_progress_label == INFERENCE_COMPLETE_PLACEHOLDER
    assert vm.judge_progress_visible is True
    assert vm.judge_progress_label == format_judge_waiting_label(0)


def test_judge_row_transitions_to_receiving_and_hides_on_completion(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-4

    The Judge progress sub-row transitions to sub-state B on a
    `context=BENCHMARK_JUDGE` progress event with `first_token_received=True`,
    then hides on `_judge_completed`. Per description.md §7.1.3's exception
    clause, the Inference progress sub-row is *not* hidden by `_judge_completed`
    alone -- it reverts to hidden only on `_task_completed`/`_task_failed`/the
    next task's `_inference_started` -- so it stays visible here, showing its
    last real (non-placeholder) label rather than the judge-phase placeholder.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    fake_event_bus.emit(SIGNAL_JUDGE_STARTED, _judge_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_INFERENCE_PROGRESS,
        _inference_progress(
            context=InferenceContext.BENCHMARK_JUDGE,
            elapsed_ms=3100,
            tokens_received=96,
            first_token_received=True,
        ),
    )
    receiving_vm = captured[-1]
    fake_event_bus.emit(SIGNAL_JUDGE_COMPLETED, _judge_completed())

    # Assert
    assert receiving_vm.judge_progress_label == format_judge_receiving_label(
        tokens=96, elapsed_ms=3100, is_estimate=False
    )
    completed_vm = captured[-1]
    assert completed_vm.judge_progress_visible is False
    assert completed_vm.inference_progress_visible is True
    assert completed_vm.inference_progress_label == format_inference_waiting_label(0)


def test_retry_line_appears_then_clears(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-5

    Covers EC-PROV-1. Given `_task_retry`, the retry line appears with the
    classified reason; given the following `_task_completed`, it clears.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_TASK_RETRY, _task_retry())
    retry_vm = captured[-1]
    fake_event_bus.emit(SIGNAL_TASK_COMPLETED, _task_completed())
    completed_vm = captured[-1]

    # Assert
    assert retry_vm.retry_active is True
    assert retry_vm.retry_label == format_retry_label(
        attempt=2, total_attempts=3, reason="Connection refused"
    )
    assert completed_vm.retry_active is False
    assert completed_vm.retry_label is None


def test_retry_with_timeout_error_kind_increments_timeouts_counter(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-5

    A `_task_retry` classified as a timeout increments the Current-task grid's
    Timeouts counter (description.md §7's "Timeouts" row).
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_TASK_RETRY, _task_retry(error_kind=ErrorKind.TIMEOUT))

    # Assert
    assert captured[-1].timeouts == 1


def test_heuristic_token_count_marked_with_tilde(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-6

    Covers EC-RUN-17. Given the active call's token-estimation source is the
    4-character heuristic, the rendered token count is prefixed with ``~``.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_INFERENCE_PROGRESS,
        _inference_progress(
            context=InferenceContext.BENCHMARK_TASK,
            elapsed_ms=4600,
            tokens_received=184,
            first_token_received=True,
            tokens_estimated=True,
        ),
    )

    # Assert
    assert captured[-1].inference_progress_label == "Generating — ~184 tokens · 4.6 s elapsed"


def test_next_task_resets_inference_row_with_no_stale_carry_over(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-059-AC-1

    The next task's `_inference_started` replaces the row with a fresh
    sub-state A — no stale label or timeout count carries over.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    fake_event_bus.emit(
        SIGNAL_INFERENCE_PROGRESS,
        _inference_progress(
            context=InferenceContext.BENCHMARK_TASK,
            elapsed_ms=5600,
            tokens_received=184,
            first_token_received=True,
        ),
    )
    fake_event_bus.emit(SIGNAL_TASK_RETRY, _task_retry(error_kind=ErrorKind.TIMEOUT))
    fake_event_bus.emit(SIGNAL_TASK_COMPLETED, _task_completed())
    captured: list[CurrentTaskViewModel] = []
    view.apply_current_task = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())

    # Assert
    vm = captured[-1]
    assert vm.inference_progress_label == format_inference_waiting_label(0)
    assert vm.timeouts == 0
    assert vm.retry_active is False


def test_format_inference_waiting_label_renders_seconds_with_one_decimal() -> None:
    assert format_inference_waiting_label(1200) == "Waiting for first token — 1.2 s"


def test_format_inference_generating_label_marks_heuristic_estimate() -> None:
    """Proves: STORY-059-AC-6

    Covers EC-RUN-17: a heuristic-sourced token count is prefixed with ``~``.
    """
    label = format_inference_generating_label(tokens=184, elapsed_ms=4600, is_estimate=True)
    assert label == "Generating — ~184 tokens · 4.6 s elapsed"


def test_format_inference_generating_label_omits_marker_for_exact_count() -> None:
    label = format_inference_generating_label(tokens=184, elapsed_ms=5600, is_estimate=False)
    assert label == "Generating — 184 tokens · 5.6 s elapsed"


def test_format_judge_waiting_label_renders_seconds_with_one_decimal() -> None:
    assert format_judge_waiting_label(2400) == "Judge: waiting for response — 2.4 s"


def test_format_judge_receiving_label_marks_heuristic_estimate() -> None:
    label = format_judge_receiving_label(tokens=96, elapsed_ms=3100, is_estimate=True)
    assert label == "Judge: receiving — ~96 tokens · 3.1 s elapsed"


def test_format_retry_label_renders_attempt_over_total_and_reason() -> None:
    """Proves: STORY-059-AC-5"""
    assert format_retry_label(attempt=2, total_attempts=3, reason="Connection refused") == (
        "2/3 - Connection refused"
    )
