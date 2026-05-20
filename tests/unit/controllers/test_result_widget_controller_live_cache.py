"""Tests for ResultWidgetController._set_detailed_summary incremental cache update logic."""

from unittest.mock import MagicMock

import pytest

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EventBus,
    TableSerializerApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    SummaryTableItem,
)
from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController


@pytest.fixture
def mock_data_api() -> MagicMock:
    return MagicMock(spec=DataApi)


@pytest.fixture
def mock_event_bus() -> MagicMock:
    return MagicMock(spec=EventBus)


@pytest.fixture
def mock_table_serializer() -> MagicMock:
    return MagicMock(spec=TableSerializerApi)


@pytest.fixture
def mock_app_settings() -> MagicMock:
    return MagicMock(spec=AppSettingsServiceApi)


@pytest.fixture
def controller(
    mock_data_api: MagicMock,
    mock_event_bus: MagicMock,
    mock_table_serializer: MagicMock,
    mock_app_settings: MagicMock,
) -> ResultWidgetController:
    return ResultWidgetController(
        data_api=mock_data_api,
        event_bus=mock_event_bus,
        table_serializer=mock_table_serializer,
        app_settings_service=mock_app_settings,
    )


def _make_result(*, model_name: str, task_id: str) -> BenchmarkResult:
    return BenchmarkResult(
        model_name=model_name,
        task_id=task_id,
        status=BenchmarkResultStatus.COMPLETED,
    )


def _make_item(*, model_name: str, task_id: str) -> SummaryTableItem:
    return SummaryTableItem(model_name=model_name, task_id=task_id)


def test_set_detailed_summary_fetches_new_keys_from_db(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    existing_result = _make_result(model_name="model_a", task_id="task_1")
    controller._selected_run_id = 1
    controller._full_results_cache["model_a|task_1|v1"] = existing_result

    new_result = _make_result(model_name="model_b", task_id="task_2")
    mock_data_api.retrieve_benchmark_results_for_run.return_value = [
        existing_result,
        new_result,
    ]

    incoming = [
        _make_item(model_name="model_a", task_id="task_1"),
        _make_item(model_name="model_b", task_id="task_2"),
    ]

    # Act
    controller._set_detailed_summary(incoming)

    # Assert
    mock_data_api.retrieve_benchmark_results_for_run.assert_called_once_with(1)
    assert "model_b|task_2|v1" in controller._full_results_cache


def test_set_detailed_summary_skips_db_when_no_new_keys(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    result_a = _make_result(model_name="model_a", task_id="task_1")
    result_b = _make_result(model_name="model_b", task_id="task_2")
    controller._selected_run_id = 1
    controller._full_results_cache["model_a|task_1|v1"] = result_a
    controller._full_results_cache["model_b|task_2|v1"] = result_b

    incoming = [
        _make_item(model_name="model_a", task_id="task_1"),
        _make_item(model_name="model_b", task_id="task_2"),
    ]

    # Act
    controller._set_detailed_summary(incoming)

    # Assert
    mock_data_api.retrieve_benchmark_results_for_run.assert_not_called()


def test_set_detailed_summary_skips_cache_update_when_run_id_is_none(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    controller._selected_run_id = None

    incoming = [_make_item(model_name="model_x", task_id="task_9")]

    # Act
    controller._set_detailed_summary(incoming)

    # Assert
    mock_data_api.retrieve_benchmark_results_for_run.assert_not_called()


def test_set_detailed_summary_handles_db_exception_gracefully(
    controller: ResultWidgetController,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    controller._selected_run_id = 1
    mock_data_api.retrieve_benchmark_results_for_run.side_effect = RuntimeError("db error")

    incoming = [_make_item(model_name="model_z", task_id="task_fail")]

    # Act / Assert — must not raise
    controller._set_detailed_summary(incoming)
