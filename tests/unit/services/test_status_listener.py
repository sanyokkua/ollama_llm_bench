"""Unit tests for StatusListener._run_id_changed — run selection, emit routing, and error handling."""

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
    BenchmarkRun,
    BenchmarkRunStatus,
    RunMode,
)
from ollama_llm_bench.ui.controllers.status_listener import StatusListener

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
# Test 1 — judge_summary set, perf_analysis_result None → only emit_judge_summary
# ---------------------------------------------------------------------------


def test_run_id_changed_emits_judge_summary_when_set(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model="model:8b",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        judge_summary="some summary text",
        perf_analysis_result=None,
    )
    mock_data_api.retrieve_benchmark_run.return_value = run
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(1)

    # Assert
    mock_event_bus.emit_judge_summary.assert_called_once()
    mock_event_bus.emit_perf_analysis.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — perf_analysis_result set, judge_summary None → only emit_perf_analysis
# ---------------------------------------------------------------------------


def test_run_id_changed_emits_perf_analysis_when_set(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=2,
        timestamp="2026-01-01T00:00:00",
        judge_model="model:8b",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        judge_summary=None,
        perf_analysis_result="perf",
    )
    mock_data_api.retrieve_benchmark_run.return_value = run
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(2)

    # Assert
    mock_event_bus.emit_perf_analysis.assert_called_once()
    mock_event_bus.emit_judge_summary.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — both fields set → both emit methods called once each
# ---------------------------------------------------------------------------


def test_run_id_changed_emits_both_when_both_set(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=3,
        timestamp="2026-01-01T00:00:00",
        judge_model="model:8b",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        judge_summary="summary text",
        perf_analysis_result="some perf text",
    )
    mock_data_api.retrieve_benchmark_run.return_value = run
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(3)

    # Assert
    mock_event_bus.emit_judge_summary.assert_called_once()
    mock_event_bus.emit_perf_analysis.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4 — both fields None → neither emit method called
# ---------------------------------------------------------------------------


def test_run_id_changed_does_not_emit_when_fields_empty(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=4,
        timestamp="2026-01-01T00:00:00",
        judge_model="model:8b",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        judge_summary=None,
        perf_analysis_result=None,
    )
    mock_data_api.retrieve_benchmark_run.return_value = run
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(4)

    # Assert
    mock_event_bus.emit_judge_summary.assert_not_called()
    mock_event_bus.emit_perf_analysis.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — run_id is None → retrieval skipped entirely
# ---------------------------------------------------------------------------


def test_run_id_changed_none_skips_retrieval(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(None)

    # Assert
    mock_data_api.retrieve_benchmark_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6 — run_id is 0 → retrieval skipped entirely
# ---------------------------------------------------------------------------


def test_run_id_changed_zero_skips_retrieval(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mocker.patch.object(listener, "_post_tables_update")

    # Act
    listener._run_id_changed(0)

    # Assert
    mock_data_api.retrieve_benchmark_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7 — retrieval raises → no exception propagates, no emit calls made
# ---------------------------------------------------------------------------


def test_run_id_changed_retrieval_error_logs_warning_and_continues(
    listener: StatusListener,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mock_data_api.retrieve_benchmark_run.side_effect = RuntimeError("not found")
    mocker.patch.object(listener, "_post_tables_update")

    # Act — must not propagate
    listener._run_id_changed(99)

    # Assert
    mock_event_bus.emit_judge_summary.assert_not_called()
