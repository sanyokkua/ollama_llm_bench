"""Unit tests for StatusListener live-update debounce and table-refresh logic."""

import time
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ResultApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResultStatus,
    EvalLayer,
    EvalVerdict,
    JudgeCompletedEvent,
    ModelDescriptor,
    PipelineStage,
    ReporterStatusMsg,
    TaskCompletedEvent,
)
from ollama_llm_bench.ui.controllers.status_listener import StatusListener

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="test-provider",
        provider_type="openai_compatible",
        model_name="llama3",
        display_label="llama3",
    )


def _make_task_completed_event(run_id: int = 1) -> TaskCompletedEvent:
    return TaskCompletedEvent(
        run_id=run_id,
        result_id=1,
        model=_make_model_descriptor(),
        task_id="task-1",
        status=BenchmarkResultStatus.COMPLETED,
        total_time_ms=100.0,
        ttft_ms=10.0,
        final_verdict=None,
    )


def _make_judge_completed_event(run_id: int = 1) -> JudgeCompletedEvent:
    return JudgeCompletedEvent(
        run_id=run_id,
        result_id=1,
        layer=EvalLayer.LLM_JUDGE,
        verdict=EvalVerdict.PASS,
        resolved=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_data_api(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=DataApi))


@pytest.fixture
def mock_flow_api(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=BenchmarkFlowApi))


@pytest.fixture
def mock_event_bus(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=EventBus))


@pytest.fixture
def mock_result_api(mocker: MockerFixture) -> MagicMock:
    api = cast(MagicMock, mocker.Mock(spec=ResultApi))
    api.retrieve_avg_benchmark_results_for_run.return_value = []
    api.retrieve_detailed_benchmark_results_for_run.return_value = []
    return api


@pytest.fixture
def listener(
    mock_data_api: MagicMock,
    mock_flow_api: MagicMock,
    mock_event_bus: MagicMock,
    mock_result_api: MagicMock,
) -> StatusListener:
    return StatusListener(
        data_api=mock_data_api,
        benchmark_flow_api=mock_flow_api,
        event_bus=mock_event_bus,
        result_api=mock_result_api,
    )


# ---------------------------------------------------------------------------
# Test 1 — debounce suppresses second call within window
# ---------------------------------------------------------------------------


def test_task_completed_within_debounce_window_skips_second_update(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange: _last_live_update far in the past so first call always fires.
    # First call at t=10.0 (passes: 10.0 - 0.0 >= 0.5), updates timestamp to 10.0.
    # Second call at t=10.1 (blocked: 10.1 - 10.0 = 0.1 < 0.5).
    listener._last_live_update = 0.0
    mocker.patch("ollama_llm_bench.ui.controllers.status_listener.time.monotonic", side_effect=[10.0, 10.1])
    event = _make_task_completed_event(run_id=1)

    # Act
    listener._on_task_or_judge_completed(event)
    listener._on_task_or_judge_completed(event)

    # Assert: only the first call triggers a table update
    mock_event_bus.emit_table_summary_data_changed.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — second call after debounce window triggers update
# ---------------------------------------------------------------------------


def test_task_completed_after_debounce_window_triggers_second_update(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange: _last_live_update is 0.0.
    # First call at t=10.0 (passes: 10.0 - 0.0 >= 0.5), updates timestamp to 10.0.
    # Second call at t=10.6 (passes: 10.6 - 10.0 = 0.6 >= 0.5).
    listener._last_live_update = 0.0
    mocker.patch("ollama_llm_bench.ui.controllers.status_listener.time.monotonic", side_effect=[10.0, 10.6])
    event = _make_task_completed_event(run_id=1)

    # Act
    listener._on_task_or_judge_completed(event)
    listener._on_task_or_judge_completed(event)

    # Assert: both calls trigger a table update
    assert mock_event_bus.emit_table_summary_data_changed.call_count == 2


# ---------------------------------------------------------------------------
# Test 3 — PipelineStage.FINISHED bypasses debounce via _progress_changed
# ---------------------------------------------------------------------------


def test_progress_finished_always_triggers_table_update(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mock_data_api: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange: stamp _last_live_update as very recent so debounce would block
    listener._last_live_update = time.monotonic()

    # data_api.retrieve_benchmark_runs used by get_benchmark_runs — return empty list
    mock_data_api.retrieve_benchmark_runs.return_value = []

    status_msg = ReporterStatusMsg(
        current_run_id=1,
        current_stage=PipelineStage.FINISHED,
    )

    # Act
    listener._progress_changed(status_msg)

    # Assert: table update was still emitted (progress path bypasses debounce)
    mock_event_bus.emit_table_summary_data_changed.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4 — JudgeCompletedEvent triggers both summary and detailed updates
# ---------------------------------------------------------------------------


def test_judge_completed_triggers_live_update(
    listener: StatusListener,
    mock_event_bus: MagicMock,
) -> None:
    # Arrange
    event = _make_judge_completed_event(run_id=1)

    # Act
    listener._on_task_or_judge_completed(event)

    # Assert: both emit methods were called
    mock_event_bus.emit_table_summary_data_changed.assert_called_once()
    mock_event_bus.emit_table_detailed_data_change.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5 — debounce resets after window expires (state is updated correctly)
# ---------------------------------------------------------------------------


def test_task_completed_debounce_timestamp_updated_on_first_call(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange: _last_live_update = 0.0, first call at t=1.0 passes debounce check
    listener._last_live_update = 0.0
    mocker.patch("ollama_llm_bench.ui.controllers.status_listener.time.monotonic", side_effect=[1.0])
    event = _make_task_completed_event(run_id=2)

    # Act
    listener._on_task_or_judge_completed(event)

    # Assert: internal timestamp was updated to 1.0
    assert listener._last_live_update == 1.0


# ---------------------------------------------------------------------------
# Test 6 — PipelineStage.FAILED also triggers table update via _progress_changed
# ---------------------------------------------------------------------------


def test_progress_failed_triggers_table_update(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    mock_data_api.retrieve_benchmark_runs.return_value = []
    status_msg = ReporterStatusMsg(
        current_run_id=5,
        current_stage=PipelineStage.FAILED,
    )

    # Act
    listener._progress_changed(status_msg)

    # Assert
    mock_event_bus.emit_table_summary_data_changed.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7 — _post_tables_update passes result_api data to event_bus emissions
# ---------------------------------------------------------------------------


def test_post_tables_update_emits_result_api_data(
    listener: StatusListener,
    mock_event_bus: MagicMock,
    mock_result_api: MagicMock,
) -> None:
    # Arrange: result_api returns sentinel lists
    avg_sentinel: list[object] = [object()]
    detailed_sentinel: list[object] = [object()]
    mock_result_api.retrieve_avg_benchmark_results_for_run.return_value = avg_sentinel
    mock_result_api.retrieve_detailed_benchmark_results_for_run.return_value = detailed_sentinel

    # Act
    listener._post_tables_update(run_id=1)

    # Assert: the sentinel values were forwarded to the event bus
    mock_event_bus.emit_table_summary_data_changed.assert_called_once_with(avg_sentinel)
    mock_event_bus.emit_table_detailed_data_change.assert_called_once_with(detailed_sentinel)


# ---------------------------------------------------------------------------
# Test 8 — _post_tables_update with None run_id emits empty lists
# ---------------------------------------------------------------------------


def test_post_tables_update_with_none_run_id_emits_empty_lists(
    listener: StatusListener,
    mock_event_bus: MagicMock,
) -> None:
    # Arrange — no extra setup needed

    # Act
    listener._post_tables_update(run_id=None)

    # Assert: empty lists emitted when no valid run_id
    mock_event_bus.emit_table_summary_data_changed.assert_called_once_with([])
    mock_event_bus.emit_table_detailed_data_change.assert_called_once_with([])
