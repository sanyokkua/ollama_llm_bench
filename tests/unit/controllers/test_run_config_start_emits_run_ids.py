"""Unit tests verifying that handle_start_click emits run_ids_changed before run_id_changed."""

from unittest.mock import MagicMock

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
    BenchmarkRun,
    BenchmarkRunStatus,
    ModelDescriptor,
    ProviderType,
    RunMode,
    RunStartEvent,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController


def _make_controller(
    data_api: MagicMock,
    event_bus: MagicMock,
    benchmark_flow_api: MagicMock,
) -> RunConfigController:
    app_settings = MagicMock(spec=AppSettingsServiceApi)
    app_settings.get_bool.return_value = False
    return RunConfigController(
        data_api=data_api,
        provider_registry=MagicMock(spec=ProviderRegistryApi),
        benchmark_flow_api=benchmark_flow_api,
        event_bus=event_bus,
        task_file_loader=MagicMock(spec=TaskFileLoaderApi),
        app_settings_service=app_settings,
        embedding_classifier=MagicMock(spec=EmbeddingModelClassifier),
        app_readiness_service=MagicMock(spec=AppReadinessServiceApi),
        name_parser=MagicMock(spec=ModelNameParser),
    )


def _make_start_event() -> RunStartEvent:
    return RunStartEvent(
        run_mode=RunMode.SPEED,
        judge_model="qwen3:8b",
        judge_provider="ollama",
        test_models=(
            ModelDescriptor(
                provider_id="ollama",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                model_name="llama3.2:3b",
                display_label="llama3.2:3b",
            ),
        ),
        task_paths=(),
    )


def test_handle_start_click_emits_run_ids_changed_before_run_id_changed() -> None:
    # Arrange
    data_api = MagicMock(spec=DataApi)
    data_api.create_benchmark_run.return_value = 42
    data_api.retrieve_benchmark_runs.return_value = [
        BenchmarkRun(
            run_id=42,
            timestamp="2026-01-01T00:00:00",
            judge_model="qwen3:8b",
            judge_provider_id="ollama",
            status=BenchmarkRunStatus.NOT_COMPLETED,
        )
    ]
    event_bus = MagicMock(spec=EventBus)
    benchmark_flow_api = MagicMock(spec=BenchmarkFlowApi)
    benchmark_flow_api.is_running.return_value = False

    controller = _make_controller(data_api, event_bus, benchmark_flow_api)

    # Act
    controller.handle_start_click(_make_start_event())

    # Assert: emit_run_ids_changed called before emit_run_id_changed
    assert event_bus.emit_run_ids_changed.called
    assert event_bus.emit_run_id_changed.called

    ids_call_idx = next(i for i, c in enumerate(event_bus.method_calls) if c[0] == "emit_run_ids_changed")
    run_id_call_idx = next(i for i, c in enumerate(event_bus.method_calls) if c[0] == "emit_run_id_changed")
    assert ids_call_idx < run_id_call_idx, "emit_run_ids_changed must fire before emit_run_id_changed"


def test_handle_start_click_emits_run_id_changed_with_new_run_id() -> None:
    # Arrange
    data_api = MagicMock(spec=DataApi)
    data_api.create_benchmark_run.return_value = 99
    data_api.retrieve_benchmark_runs.return_value = []
    event_bus = MagicMock(spec=EventBus)
    benchmark_flow_api = MagicMock(spec=BenchmarkFlowApi)
    benchmark_flow_api.is_running.return_value = False

    controller = _make_controller(data_api, event_bus, benchmark_flow_api)

    # Act
    controller.handle_start_click(_make_start_event())

    # Assert
    event_bus.emit_run_id_changed.assert_called_once_with(99)
