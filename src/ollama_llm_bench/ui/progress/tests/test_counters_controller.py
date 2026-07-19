"""Colocated ``CountersController`` tests for ``ui/progress/`` (STORY-058-AC-4, AC-5)."""

from typing import TYPE_CHECKING

from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import BenchmarkRun, ResultStatus, RunMode, RunStatus
from ollama_llm_bench.backend.events import (
    SIGNAL_PROGRESS_UPDATED,
    SIGNAL_RUN_STARTED,
    ProgressUpdatedEvent,
    RunStartedEvent,
)
from ollama_llm_bench.ui.progress._internal.counters_controller import CountersController
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus

if TYPE_CHECKING:
    from ollama_llm_bench.ui.progress.models import CountersViewModel

_FAILURE_STATUSES = (
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)
_EXPECTED_PENDING = 3
_EXPECTED_KEYWORD_WAIT = 1
_EXPECTED_JUDGE_WAIT = 2
_EXPECTED_COMPLETED = 1
_EXPECTED_FAILED_TOTAL = 2
_LAST_BURST_COMPLETED = 5


def _run_started_event(run_id: int = 1) -> RunStartedEvent:
    return RunStartedEvent(
        run_id=run_id,
        run_name="Run 1",
        run_mode=RunMode.GRADED,
        started_at="2026-01-01T00:00:00Z",
        total_tasks=10,
        test_targets=(("prov-1", "model-1"),),
        judge_target=("prov-1", "judge-model"),
    )


def _progress_event(
    counts: dict[ResultStatus, int], *, completed: int, total: int = 10
) -> ProgressUpdatedEvent:
    return ProgressUpdatedEvent(
        run_id=1,
        completed_count=completed,
        total_count=total,
        counts_by_result_status=counts,
        current_provider_id="prov-1",
        current_model_name="model-1",
    )


def _make_run_header() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        run_name="Run 1",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=RunMode.GRADED,
        status=RunStatus.INCOMPLETE,
        total_tasks=10,
        completed_tasks=0,
        total_elapsed_ms=1000,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
    )


def _bind(
    *, gateway: FakeProgressGateway, event_bus: FakeEventBus, qtbot: QtBot
) -> tuple[CountersController, ProgressView]:
    view = ProgressView()
    qtbot.addWidget(view)
    controller = CountersController(gateway=gateway, event_bus=event_bus)
    controller.bind(view)
    return controller, view


def test_counts_by_status_maps_to_counters_and_segments(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-4

    Given a `_progress_updated` event carrying a `counts_by_status` map, each
    counter equals the map value for its `ResultStatus`, the Failed counter
    equals the sum of the five terminal-failure statuses, and the stage-bar
    segment weights derive from the same map.
    """
    # Arrange
    fake_gateway.set_run_header(_make_run_header())
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    counts = {
        ResultStatus.PENDING: _EXPECTED_PENDING,
        ResultStatus.AWAITING_KEYWORD_CHECK: _EXPECTED_KEYWORD_WAIT,
        ResultStatus.AWAITING_COSINE_CHECK: 1,
        ResultStatus.AWAITING_JUDGE_CHECK: _EXPECTED_JUDGE_WAIT,
        ResultStatus.COMPLETED: _EXPECTED_COMPLETED,
        ResultStatus.FAILED_INFERENCE: 1,
        ResultStatus.FAILED_PROVIDER: 1,
        ResultStatus.FAILED_TIMEOUT: 0,
        ResultStatus.FAILED_JUDGE_TIMEOUT: 0,
        ResultStatus.ERRORED: 0,
    }
    captured: list[CountersViewModel] = []
    view.apply_counters = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_PROGRESS_UPDATED, _progress_event(counts, completed=6))
    qtbot.wait(50)

    # Assert
    vm = captured[-1]
    assert vm.counts_by_status[ResultStatus.PENDING] == _EXPECTED_PENDING
    assert vm.counts_by_status[ResultStatus.AWAITING_KEYWORD_CHECK] == _EXPECTED_KEYWORD_WAIT
    assert vm.counts_by_status[ResultStatus.AWAITING_JUDGE_CHECK] == _EXPECTED_JUDGE_WAIT
    assert vm.counts_by_status[ResultStatus.COMPLETED] == _EXPECTED_COMPLETED
    failed_total = sum(counts[status] for status in _FAILURE_STATUSES)
    assert failed_total == _EXPECTED_FAILED_TOTAL
    badges = dict(vm.badge_counts)
    assert badges["failed"] == failed_total
    bar_segments = dict(vm.bar_segments)
    assert bar_segments["failed"] == failed_total
    assert bar_segments["pending"] == _EXPECTED_PENDING


def test_progress_updated_bursts_coalesce(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-5

    Given a burst of consecutive `_progress_updated` events, the
    CountersController coalesces the burst and the last payload wins for the
    refreshed counters.
    """
    # Arrange
    fake_gateway.set_run_header(_make_run_header())
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    captured: list[CountersViewModel] = []
    view.apply_counters = captured.append  # type: ignore[method-assign, assignment]

    # Act -- a burst of five events within the same event-loop turn
    for completed in range(1, _LAST_BURST_COMPLETED + 1):
        fake_event_bus.emit(
            SIGNAL_PROGRESS_UPDATED,
            _progress_event({ResultStatus.PENDING: 10 - completed}, completed=completed),
        )
    qtbot.wait(50)

    # Assert -- exactly one repaint, reflecting the last payload
    assert len(captured) == 1
    assert captured[0].tasks_done == _LAST_BURST_COMPLETED
