"""Unit tests for RunConfigController — provider discovery, run management, benchmark lifecycle."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkRun,
    BenchmarkRunStatus,
    RunMode,
    RunStartEvent,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mocks(mocker: MockerFixture) -> SimpleNamespace:
    """Return a namespace with all mocked dependencies."""
    return SimpleNamespace(
        data_api=mocker.Mock(spec=DataApi),
        provider_registry=mocker.Mock(spec=ProviderRegistryApi),
        benchmark_flow_api=mocker.Mock(spec=BenchmarkFlowApi),
        event_bus=mocker.Mock(spec=EventBus),
        task_file_loader=mocker.Mock(spec=TaskFileLoaderApi),
        app_settings_service=mocker.Mock(spec=AppSettingsServiceApi),
        embedding_classifier=EmbeddingModelClassifier(),
    )


@pytest.fixture
def controller(mocks: SimpleNamespace) -> RunConfigController:
    """Return a RunConfigController with all injected mocks."""
    return RunConfigController(
        data_api=mocks.data_api,
        provider_registry=mocks.provider_registry,
        benchmark_flow_api=mocks.benchmark_flow_api,
        event_bus=mocks.event_bus,
        task_file_loader=mocks.task_file_loader,
        app_settings_service=mocks.app_settings_service,
        embedding_classifier=mocks.embedding_classifier,
    )


def _make_run(
    run_id: int,
    timestamp: str,
    status: BenchmarkRunStatus,
) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        timestamp=timestamp,
        judge_model="llama3",
        status=status,
    )


def _make_start_event(
    test_models: tuple[str, ...] = ("model_a",),
    task_paths: tuple[Path, ...] = (),
) -> RunStartEvent:
    return RunStartEvent(
        run_mode=RunMode.FULL_GRADING,
        judge_provider="provider_a",
        judge_model="llama3",
        test_provider="provider_a",
        test_models=test_models,
        task_paths=task_paths,
    )


# ---------------------------------------------------------------------------
# Provider / model discovery
# ---------------------------------------------------------------------------


def test_get_provider_names_returns_enabled_provider_ids(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    provider_a = SimpleNamespace(provider_id="provider_a")
    provider_b = SimpleNamespace(provider_id="provider_b")
    mocks.provider_registry.get_enabled_providers.return_value = [provider_a, provider_b]

    # Act
    result = controller.get_provider_names()

    # Assert
    assert result == ["provider_a", "provider_b"]


def test_get_provider_names_returns_empty_list_on_exception(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.provider_registry.get_enabled_providers.side_effect = RuntimeError("registry down")

    # Act
    result = controller.get_provider_names()

    # Assert
    assert result == []


def test_get_models_for_provider_returns_model_names(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    model_a = SimpleNamespace(model_name="model_a")
    model_b = SimpleNamespace(model_name="model_b")
    mock_provider = SimpleNamespace(get_available_models=lambda: [model_a, model_b])
    mocks.provider_registry.get_provider.return_value = mock_provider

    # Act
    result = controller.get_models_for_provider("provider_a")

    # Assert
    assert result == ["model_a", "model_b"]


def test_get_models_for_provider_returns_empty_on_exception(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.provider_registry.get_provider.side_effect = KeyError("provider_a")

    # Act
    result = controller.get_models_for_provider("provider_a")

    # Assert
    assert result == []


# ---------------------------------------------------------------------------
# Previous-run management
# ---------------------------------------------------------------------------


def test_get_unfinished_runs_returns_not_completed_sorted_newest_first(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — 2 NOT_COMPLETED with different timestamps, 1 COMPLETED
    older = _make_run(1, "2024-01-01T08:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    newer = _make_run(2, "2024-06-15T12:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    completed = _make_run(3, "2024-12-31T23:59:59", BenchmarkRunStatus.COMPLETED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [older, newer, completed]

    # Act
    result = controller.get_unfinished_runs()

    # Assert — only the 2 NOT_COMPLETED, newest timestamp first
    assert len(result) == 2
    assert result[0] == (2, "2024-06-15T12:00:00")
    assert result[1] == (1, "2024-01-01T08:00:00")


def test_get_unfinished_runs_returns_empty_list_on_exception(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.data_api.retrieve_benchmark_runs.side_effect = RuntimeError("db error")

    # Act
    result = controller.get_unfinished_runs()

    # Assert
    assert result == []


# ---------------------------------------------------------------------------
# Benchmark lifecycle — handle_start_click
# ---------------------------------------------------------------------------


def test_handle_start_click_creates_run_and_starts_execution(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.create_benchmark_run.return_value = 42
    mocks.task_file_loader.load_tasks.return_value = []
    event = _make_start_event(test_models=("model_a",))

    # Act
    controller.handle_start_click(event)

    # Assert
    mocks.data_api.create_benchmark_run.assert_called_once()
    mocks.benchmark_flow_api.start_execution.assert_called_once_with(42)


def test_handle_start_click_does_nothing_when_already_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = True
    event = _make_start_event()

    # Act
    controller.handle_start_click(event)

    # Assert
    mocks.data_api.create_benchmark_run.assert_not_called()


def test_handle_start_click_emits_global_msg_and_returns_when_already_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = True
    event = _make_start_event()

    # Act
    controller.handle_start_click(event)

    # Assert
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Benchmark already running.")


def test_handle_start_click_emits_global_msg_when_no_models_selected(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    event = _make_start_event(test_models=())

    # Act
    controller.handle_start_click(event)

    # Assert
    mocks.data_api.create_benchmark_run.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("No test models selected.")


def test_handle_start_click_emits_run_id_changed_and_log_clean_on_success(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.create_benchmark_run.return_value = 7
    mocks.task_file_loader.load_tasks.return_value = []
    event = _make_start_event()

    # Act
    controller.handle_start_click(event)

    # Assert
    mocks.event_bus.emit_run_id_changed.assert_called_once_with(7)
    mocks.event_bus.emit_log_clean.assert_called_once()


# ---------------------------------------------------------------------------
# Benchmark lifecycle — handle_pause_click / handle_stop_click
# ---------------------------------------------------------------------------


def test_handle_pause_click_delegates_to_flow_api(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = True

    # Act
    controller.handle_pause_click()

    # Assert
    mocks.benchmark_flow_api.pause_execution.assert_called_once()


def test_handle_pause_click_does_nothing_when_not_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False

    # Act
    controller.handle_pause_click()

    # Assert
    mocks.benchmark_flow_api.pause_execution.assert_not_called()


def test_handle_stop_click_delegates_to_flow_api(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = True

    # Act
    controller.handle_stop_click()

    # Assert
    mocks.benchmark_flow_api.stop_execution.assert_called_once()


def test_handle_stop_click_does_nothing_when_not_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False

    # Act
    controller.handle_stop_click()

    # Assert
    mocks.benchmark_flow_api.stop_execution.assert_not_called()


# ---------------------------------------------------------------------------
# Benchmark lifecycle — handle_resume_run_click
# ---------------------------------------------------------------------------


def test_handle_resume_run_click_starts_execution_for_valid_run(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    run = _make_run(7, "2024-01-01T10:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [run]

    # Act
    controller.handle_resume_run_click(7)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_called_once_with(7)


def test_handle_resume_run_click_does_nothing_when_already_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = True

    # Act
    controller.handle_resume_run_click(7)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Benchmark already running.")


def test_handle_resume_run_click_emits_msg_when_run_not_found(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.retrieve_benchmark_runs.return_value = []

    # Act
    controller.handle_resume_run_click(99)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Run 99 not found.")


def test_handle_resume_run_click_emits_msg_when_run_already_completed(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    run = _make_run(5, "2024-01-01T10:00:00", BenchmarkRunStatus.COMPLETED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [run]

    # Act
    controller.handle_resume_run_click(5)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Run 5 is already completed.")


def test_handle_resume_run_click_emits_run_id_changed_on_success(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    run = _make_run(7, "2024-01-01T10:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [run]

    # Act
    controller.handle_resume_run_click(7)

    # Assert
    mocks.event_bus.emit_run_id_changed.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# Constructor subscription wiring
# ---------------------------------------------------------------------------


def test_constructor_subscribes_to_background_thread_running(
    mocks: SimpleNamespace,
) -> None:
    # Act — construct controller
    RunConfigController(
        data_api=mocks.data_api,
        provider_registry=mocks.provider_registry,
        benchmark_flow_api=mocks.benchmark_flow_api,
        event_bus=mocks.event_bus,
        task_file_loader=mocks.task_file_loader,
        app_settings_service=mocks.app_settings_service,
        embedding_classifier=mocks.embedding_classifier,
    )

    # Assert
    mocks.event_bus.subscribe_to_background_thread_is_running.assert_called_once()


# ---------------------------------------------------------------------------
# Subscription delegation
# ---------------------------------------------------------------------------


def test_subscribe_to_benchmark_status_change_delegates_to_event_bus(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    def callback(is_running: bool) -> None:
        pass

    # Act
    controller.subscribe_to_benchmark_status_change(callback)

    # Assert
    mocks.event_bus.subscribe_to_background_thread_is_running.assert_called_with(callback)


def test_subscribe_to_runs_change_delegates_to_event_bus(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    def callback(runs: list[tuple[int, str]]) -> None:
        pass

    # Act
    controller.subscribe_to_runs_change(callback)

    # Assert
    mocks.event_bus.subscribe_to_run_ids_changed.assert_called_once_with(callback)


# ---------------------------------------------------------------------------
# Internal _on_background_changed handler
# ---------------------------------------------------------------------------


def test_on_background_changed_emits_run_ids_when_stopped(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — one NOT_COMPLETED run exists
    run = _make_run(3, "2024-03-01T09:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [run]

    # Act — simulate background thread finishing (is_running → False)
    controller._on_background_changed(False)  # testing internal handler

    # Assert
    mocks.event_bus.emit_run_ids_changed.assert_called_once_with([(3, "2024-03-01T09:00:00")])


def test_on_background_changed_does_not_emit_when_running(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Act — background thread just started (is_running → True)
    controller._on_background_changed(True)

    # Assert — no emission while still running
    mocks.event_bus.emit_run_ids_changed.assert_not_called()


# ---------------------------------------------------------------------------
# get_recent_runs
# ---------------------------------------------------------------------------


def test_get_recent_runs_orders_by_timestamp_desc(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — three runs in arbitrary order
    jan = _make_run(1, "2024-01-01T08:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    jun = _make_run(2, "2024-06-15T12:00:00", BenchmarkRunStatus.COMPLETED)
    dec = _make_run(3, "2024-12-31T23:59:59", BenchmarkRunStatus.FAILED)
    mocks.data_api.retrieve_benchmark_runs.return_value = [jan, dec, jun]

    # Act
    result = controller.get_recent_runs()

    # Assert — newest-first order; all three statuses present
    assert len(result) == 3
    assert result[0].run_id == 3  # dec
    assert result[1].run_id == 2  # jun
    assert result[2].run_id == 1  # jan
    statuses = {r.status for r in result}
    assert BenchmarkRunStatus.NOT_COMPLETED in statuses
    assert BenchmarkRunStatus.COMPLETED in statuses
    assert BenchmarkRunStatus.FAILED in statuses


def test_get_recent_runs_respects_limit(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — 200 runs
    runs = [_make_run(i, f"2024-01-{i:02d}T00:00:00", BenchmarkRunStatus.NOT_COMPLETED) for i in range(1, 29)]
    runs += [_make_run(i, f"2024-02-{i:02d}T00:00:00", BenchmarkRunStatus.NOT_COMPLETED) for i in range(1, 29)]
    runs += [_make_run(i + 56, f"2024-03-{i:02d}T00:00:00", BenchmarkRunStatus.NOT_COMPLETED) for i in range(1, 29)]
    runs += [_make_run(i + 84, f"2024-04-{i:02d}T00:00:00", BenchmarkRunStatus.NOT_COMPLETED) for i in range(1, 17)]
    # total = 28 + 28 + 28 + 16 = 100; add more to cross the 100 threshold
    extra = [_make_run(200 + i, f"2025-01-{i:02d}T00:00:00", BenchmarkRunStatus.NOT_COMPLETED) for i in range(1, 28)]
    mocks.data_api.retrieve_benchmark_runs.return_value = runs + extra

    # Act
    result = controller.get_recent_runs()

    # Assert
    assert len(result) == 100


def test_get_recent_runs_returns_empty_list_on_exception(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.data_api.retrieve_benchmark_runs.side_effect = RuntimeError("db error")

    # Act
    result = controller.get_recent_runs()

    # Assert
    assert result == []
