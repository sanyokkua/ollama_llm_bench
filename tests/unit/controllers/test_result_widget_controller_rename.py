"""Unit tests for ResultWidgetController rename functionality."""

from unittest.mock import MagicMock

import pytest

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EventBus,
    TableSerializerApi,
)
from ollama_llm_bench.backend.core.models import BenchmarkRun, BenchmarkRunStatus, RunRenamedEvent
from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController


@pytest.fixture
def mock_data_api() -> MagicMock:
    return MagicMock(spec=DataApi)


@pytest.fixture
def mock_event_bus() -> MagicMock:
    return MagicMock(spec=EventBus)


@pytest.fixture
def controller(mock_data_api: MagicMock, mock_event_bus: MagicMock) -> ResultWidgetController:
    return ResultWidgetController(
        data_api=mock_data_api,
        event_bus=mock_event_bus,
        table_serializer=MagicMock(spec=TableSerializerApi),
        app_settings_service=MagicMock(spec=AppSettingsServiceApi),
    )


def _make_run(run_id: int, run_name: str | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        timestamp=f"2026-01-01T00:0{run_id}:00",
        status=BenchmarkRunStatus.COMPLETED,
        judge_model="qwen3:8b",
        run_name=run_name,
    )


def test_rename_run_calls_data_api(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = []

    controller.rename_run(run_id=42, new_name="My Run")

    mock_data_api.update_run_name.assert_called_once_with(run_id=42, run_name="My Run")


def test_rename_run_emits_run_renamed_event(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = []

    controller.rename_run(run_id=7, new_name="Renamed")

    mock_event_bus.emit_run_renamed.assert_called_once_with(RunRenamedEvent(run_id=7, new_name="Renamed"))


def test_rename_run_refreshes_run_ids(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = [_make_run(1, "Renamed")]

    controller.rename_run(run_id=1, new_name="Renamed")

    mock_event_bus.emit_run_ids_changed.assert_called_once()


def test_get_run_names_excludes_given_run_id(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = [
        _make_run(1, "Alpha"),
        _make_run(2, "Beta"),
        _make_run(3, None),
    ]

    names = controller.get_run_names(exclude_run_id=1)

    assert names == frozenset({"beta"})


def test_get_run_names_without_exclusion(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = [
        _make_run(1, "Alpha"),
        _make_run(2, "Beta"),
    ]

    names = controller.get_run_names()

    assert names == frozenset({"alpha", "beta"})


def test_get_run_names_ignores_null_names(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    mock_data_api.retrieve_benchmark_runs.return_value = [
        _make_run(1, None),
        _make_run(2, None),
        _make_run(3, "Named"),
    ]

    names = controller.get_run_names()

    assert names == frozenset({"named"})
