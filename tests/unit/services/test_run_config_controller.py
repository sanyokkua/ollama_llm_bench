"""Unit tests for RunConfigController — provider discovery, run management, benchmark lifecycle."""

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppReadinessServiceApi,
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    ModelDescriptor,
    ReadinessVerdict,
    RunMode,
    RunStartEvent,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController

_DESCRIPTOR_A = ModelDescriptor(
    provider_id="provider_a",
    provider_type="openai_compatible",
    model_name="model_a",
    display_label="provider_a / model_a",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mocks(mocker: MockerFixture) -> SimpleNamespace:
    """Return a namespace with all mocked dependencies."""
    mock_readiness = mocker.Mock(spec=AppReadinessServiceApi)
    mock_readiness.verdict_for.return_value = ReadinessVerdict(
        mode=RunMode.SPEED, is_ready=True, issues=(), severity="ok"
    )
    mock_provider_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_provider = mocker.Mock()
    mock_provider.provider_type = "openai_compatible"
    mock_provider.get_available_models.return_value = []
    mock_provider_registry.get_provider.return_value = mock_provider
    return SimpleNamespace(
        data_api=mocker.Mock(spec=DataApi),
        provider_registry=mock_provider_registry,
        benchmark_flow_api=mocker.Mock(spec=BenchmarkFlowApi),
        event_bus=mocker.Mock(spec=EventBus),
        task_file_loader=mocker.Mock(spec=TaskFileLoaderApi),
        app_settings_service=mocker.Mock(spec=AppSettingsServiceApi),
        embedding_classifier=EmbeddingModelClassifier(),
        app_readiness_service=mock_readiness,
        name_parser=ModelNameParser(),
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
        app_readiness_service=mocks.app_readiness_service,
        name_parser=mocks.name_parser,
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
    test_models: tuple[ModelDescriptor, ...] = (_DESCRIPTOR_A,),
    task_paths: tuple[Path, ...] = (),
    run_mode: RunMode = RunMode.FULL_GRADING,
) -> RunStartEvent:
    return RunStartEvent(
        run_mode=run_mode,
        judge_provider="provider_a",
        judge_model="llama3",
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
    event = _make_start_event(test_models=(_DESCRIPTOR_A,))

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
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = []

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
    # Arrange — retrieve_benchmark_run raises ValueError when run doesn't exist
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.retrieve_benchmark_run.side_effect = ValueError("not found")

    # Act
    controller.handle_resume_run_click(99)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Failed to resume run.")


def test_handle_resume_run_click_emits_msg_when_run_not_resumable(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — COMPLETED run with no non-terminal results
    mocks.benchmark_flow_api.is_running.return_value = False
    run = _make_run(5, "2024-01-01T10:00:00", BenchmarkRunStatus.COMPLETED)
    completed_result = dataclasses.replace(_make_result(5), status=BenchmarkResultStatus.COMPLETED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = [completed_result]

    # Act
    controller.handle_resume_run_click(5)

    # Assert
    mocks.benchmark_flow_api.start_execution.assert_not_called()
    mocks.event_bus.emit_global_event_msg.assert_called_once_with("Run 5 is not resumable.")


def test_handle_resume_run_click_emits_run_id_changed_on_success(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    run = _make_run(7, "2024-01-01T10:00:00", BenchmarkRunStatus.NOT_COMPLETED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = []

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
        app_readiness_service=mocks.app_readiness_service,
        name_parser=mocks.name_parser,
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
    mocks.event_bus.subscribe_to_background_thread_is_running.assert_called_with(callback, parent=None)


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
    mocks.event_bus.subscribe_to_run_ids_changed.assert_called_once_with(callback, parent=None)


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


def test_handle_start_click_persists_multi_provider_models_json(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    """Models from two different providers must both appear in models_json."""
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.create_benchmark_run.return_value = 10
    mocks.task_file_loader.load_tasks.return_value = []
    desc_ollama = ModelDescriptor(
        provider_id="ollama_local",
        provider_type="openai_compatible",
        model_name="llama3.1:8b",
        display_label="ollama_local / llama3.1:8b",
    )
    desc_lm_studio = ModelDescriptor(
        provider_id="lm_studio_local",
        provider_type="openai_compatible",
        model_name="mistral-7b",
        display_label="lm_studio_local / mistral-7b",
    )
    event = _make_start_event(test_models=(desc_ollama, desc_lm_studio))

    # Act
    controller.handle_start_click(event)

    # Assert — both providers survive into models_json
    call_args = mocks.data_api.create_benchmark_run.call_args
    run_arg: BenchmarkRun = call_args.args[0]
    models = json.loads(run_arg.models_json)
    provider_ids = {m["provider_id"] for m in models}
    assert provider_ids == {"ollama_local", "lm_studio_local"}
    assert len(models) == 2


def test_handle_start_click_performance_mode_allows_empty_test_models(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    """Performance mode must not be blocked by the empty-test-models guard."""
    # Arrange
    mocks.benchmark_flow_api.is_running.return_value = False
    mocks.data_api.create_benchmark_run.return_value = 20
    event = _make_start_event(test_models=(), run_mode=RunMode.PERFORMANCE)

    # Act
    controller.handle_start_click(event)

    # Assert — run was created (not rejected)
    mocks.data_api.create_benchmark_run.assert_called_once()
    mocks.event_bus.emit_global_event_msg.assert_not_called()


# ---------------------------------------------------------------------------
# Resume gate tests
# ---------------------------------------------------------------------------


def _make_result(
    run_id: int,
    *,
    result_id: int = 1,
    status: BenchmarkResultStatus = BenchmarkResultStatus.NOT_COMPLETED,
) -> BenchmarkResult:
    return BenchmarkResult(run_id=run_id, result_id=result_id, task_id="t1", model_name="m1")


def test_resume_gate_accepts_stopped_run(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    run = _make_run(10, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = []

    # Act & Assert
    assert controller.is_run_resumable(10) is True


def test_resume_gate_accepts_failed_run(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    run = _make_run(11, "2026-01-01T00:00:00", BenchmarkRunStatus.FAILED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = []

    assert controller.is_run_resumable(11) is True


def test_resume_gate_accepts_completed_run_with_non_terminal_results(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — run is COMPLETED but has a WAITING_FOR_JUDGE result
    run = _make_run(12, "2026-01-01T00:00:00", BenchmarkRunStatus.COMPLETED)
    result = dataclasses.replace(_make_result(12), status=BenchmarkResultStatus.WAITING_FOR_JUDGE)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = [result]

    assert controller.is_run_resumable(12) is True


def test_resume_gate_rejects_fully_completed_run(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — all results are terminal
    run = _make_run(13, "2026-01-01T00:00:00", BenchmarkRunStatus.COMPLETED)
    result = dataclasses.replace(_make_result(13), status=BenchmarkResultStatus.COMPLETED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = [result]

    assert controller.is_run_resumable(13) is False


def test_resume_resets_status_to_not_completed_before_start_execution(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — STOPPED run
    run = _make_run(14, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    mocks.data_api.retrieve_benchmark_run.return_value = run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = []
    mocks.benchmark_flow_api.is_running.return_value = False

    # Act
    controller.handle_resume_run_click(14)

    # Assert — update_benchmark_run called with NOT_COMPLETED before start_execution
    mocks.data_api.update_benchmark_run.assert_called_once()
    updated_run: BenchmarkRun = mocks.data_api.update_benchmark_run.call_args.args[0]
    assert updated_run.status == BenchmarkRunStatus.NOT_COMPLETED
    mocks.benchmark_flow_api.start_execution.assert_called_once_with(14)


# ---------------------------------------------------------------------------
# clone_run_for_retry tests
# ---------------------------------------------------------------------------


def test_clone_run_for_retry_creates_new_run(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange
    original_run = _make_run(20, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    results = [_make_result(20, result_id=1, status=BenchmarkResultStatus.NOT_COMPLETED)]
    mocks.data_api.retrieve_benchmark_run.return_value = original_run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = results
    mocks.data_api.create_benchmark_run.return_value = 99

    # Act
    new_id = controller.clone_run_for_retry(20)

    # Assert
    assert new_id == 99
    mocks.data_api.create_benchmark_run.assert_called_once()
    created_run: BenchmarkRun = mocks.data_api.create_benchmark_run.call_args.args[0]
    assert created_run.status == BenchmarkRunStatus.NOT_COMPLETED
    assert created_run.run_id == 0


def test_clone_run_preserves_only_non_terminal_results_by_default(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    # Arrange — one COMPLETED result and one NOT_COMPLETED result
    original_run = _make_run(21, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    completed_result = dataclasses.replace(_make_result(21, result_id=1), status=BenchmarkResultStatus.COMPLETED)
    pending_result = dataclasses.replace(_make_result(21, result_id=2), status=BenchmarkResultStatus.NOT_COMPLETED)
    mocks.data_api.retrieve_benchmark_run.return_value = original_run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = [completed_result, pending_result]
    mocks.data_api.create_benchmark_run.return_value = 100

    # Act
    controller.clone_run_for_retry(21)

    # Assert — retryable result reset to NOT_COMPLETED; clean COMPLETED result preserved as-is
    mocks.data_api.create_benchmark_results.assert_called_once()
    cloned_results: list[BenchmarkResult] = mocks.data_api.create_benchmark_results.call_args.args[0]
    assert len(cloned_results) == 2
    statuses = {r.status for r in cloned_results}
    assert BenchmarkResultStatus.NOT_COMPLETED in statuses
    assert BenchmarkResultStatus.COMPLETED in statuses


def test_clone_run_for_retry_preserves_completed_results_and_resets_failed(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    """Gap 4: clone preserves clean COMPLETED rows and resets FAILED rows to NOT_COMPLETED."""
    # Arrange — 2 COMPLETED (clean), 2 FAILED, 1 WAITING_FOR_JUDGE
    original_run = _make_run(22, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    results = [
        dataclasses.replace(_make_result(22, result_id=1), status=BenchmarkResultStatus.COMPLETED),
        dataclasses.replace(_make_result(22, result_id=2), status=BenchmarkResultStatus.COMPLETED),
        dataclasses.replace(_make_result(22, result_id=3), status=BenchmarkResultStatus.FAILED),
        dataclasses.replace(_make_result(22, result_id=4), status=BenchmarkResultStatus.FAILED),
        dataclasses.replace(_make_result(22, result_id=5), status=BenchmarkResultStatus.WAITING_FOR_JUDGE),
    ]
    mocks.data_api.retrieve_benchmark_run.return_value = original_run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = results
    mocks.data_api.create_benchmark_run.return_value = 200

    # Act
    controller.clone_run_for_retry(22)

    # Assert — 5 total results: 2 COMPLETED preserved + 3 reset to NOT_COMPLETED
    mocks.data_api.create_benchmark_results.assert_called_once()
    cloned: list[BenchmarkResult] = mocks.data_api.create_benchmark_results.call_args.args[0]
    assert len(cloned) == 5
    completed_count = sum(1 for r in cloned if r.status == BenchmarkResultStatus.COMPLETED)
    not_completed_count = sum(1 for r in cloned if r.status == BenchmarkResultStatus.NOT_COMPLETED)
    assert completed_count == 2
    assert not_completed_count == 3


def test_clone_run_for_retry_includes_failed_results_in_default_selection(
    controller: RunConfigController,
    mocks: SimpleNamespace,
) -> None:
    """Gap 3: default auto-selection includes FAILED results (not just NOT_COMPLETED)."""
    original_run = _make_run(23, "2026-01-01T00:00:00", BenchmarkRunStatus.STOPPED)
    failed_result = dataclasses.replace(_make_result(23, result_id=1), status=BenchmarkResultStatus.FAILED)
    mocks.data_api.retrieve_benchmark_run.return_value = original_run
    mocks.data_api.retrieve_benchmark_results_for_run.return_value = [failed_result]
    mocks.data_api.create_benchmark_run.return_value = 300

    controller.clone_run_for_retry(23)

    mocks.data_api.create_benchmark_results.assert_called_once()
    cloned: list[BenchmarkResult] = mocks.data_api.create_benchmark_results.call_args.args[0]
    assert len(cloned) == 1
    assert cloned[0].status == BenchmarkResultStatus.NOT_COMPLETED
