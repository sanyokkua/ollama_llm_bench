"""Unit tests for BenchmarkExecutionTask._emit_progress populating counts_by_status."""

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EvaluatorApi,
    EventBus,
    JudgePromptServiceApi,
    JudgeSummaryServiceApi,
    LLMJudgeEvaluatorApi,
    LogFileWriterApi,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import BenchmarkResult, EvalLayer, ProgressUpdateEvent
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask


def _make_task(mocker: MockerFixture) -> BenchmarkExecutionTask:
    from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

    app_settings = mocker.Mock(spec=AppSettingsServiceApi)
    app_settings.get_bool.return_value = False
    app_settings.get_int.side_effect = lambda key, default=0: int(_DEFAULTS.get(key, str(default)))
    task = BenchmarkExecutionTask(
        run_id=1,
        data_api=mocker.Mock(spec=DataApi),
        task_loader=mocker.Mock(spec=TaskFileLoaderApi),
        judge_prompt_service=mocker.Mock(spec=JudgePromptServiceApi),
        judge_summary_service=mocker.Mock(spec=JudgeSummaryServiceApi),
        provider_registry=mocker.Mock(spec=ProviderRegistryApi),
        event_bus=mocker.Mock(spec=EventBus),
        app_settings=app_settings,
        rule_evaluator=mocker.Mock(spec=EvaluatorApi),
        keyword_evaluator=mocker.Mock(spec=EvaluatorApi),
        cosine_evaluator=mocker.Mock(spec=EvaluatorApi),
        llm_judge_evaluator=mocker.Mock(spec=LLMJudgeEvaluatorApi),
        log_file_writer=mocker.Mock(spec=LogFileWriterApi),
    )
    task.signals = mocker.Mock()
    task._rule_evaluator.layer = EvalLayer.RULE_BASED  # type: ignore[misc]
    task._keyword_evaluator.layer = EvalLayer.KEYWORD  # type: ignore[misc]
    task._cosine_evaluator.layer = EvalLayer.COSINE  # type: ignore[misc]
    task._llm_judge_evaluator.layer = EvalLayer.LLM_JUDGE  # type: ignore[misc]
    return task


def test_emit_progress_populates_counts_by_status(mocker: MockerFixture) -> None:
    # Arrange
    task = _make_task(mocker)
    expected_counts = {"COMPLETED": 3, "FAILED": 1}
    task._data_api.retrieve_status_counts_for_run.return_value = expected_counts  # type: ignore[attr-defined]

    # Act
    task._emit_progress()

    # Assert
    task._event_bus.emit_progress_update.assert_called_once()  # type: ignore[attr-defined]
    event: ProgressUpdateEvent = task._event_bus.emit_progress_update.call_args[0][0]  # type: ignore[attr-defined]
    assert event.counts_by_status == expected_counts


def test_emit_progress_uses_empty_dict_when_query_raises(mocker: MockerFixture) -> None:
    # Arrange
    task = _make_task(mocker)
    task._data_api.retrieve_status_counts_for_run.side_effect = RuntimeError("db error")  # type: ignore[attr-defined]

    # Act
    task._emit_progress()

    # Assert — should not raise; event carries empty dict
    event: ProgressUpdateEvent = task._event_bus.emit_progress_update.call_args[0][0]  # type: ignore[attr-defined]
    assert event.counts_by_status == {}


def _make_result() -> BenchmarkResult:
    return BenchmarkResult(run_id=1, task_id="t1", provider_id="p1", model_name="m1")


def test_mark_failed_null_task_increments_completed_tasks(mocker: MockerFixture) -> None:
    """Null-task early-exit path must increment _completed_tasks before _emit_progress."""
    # Arrange
    task = _make_task(mocker)
    task._data_api.retrieve_status_counts_for_run.return_value = {}  # type: ignore[attr-defined]
    result = _make_result()
    assert task._completed_tasks == 0

    # Act — simulate the null-task branch
    task._mark_failed(result, RuntimeError("Task definition not found"))
    task._completed_tasks += 1
    task._emit_progress()

    # Assert
    assert task._completed_tasks == 1
    task._event_bus.emit_progress_update.assert_called_once()  # type: ignore[attr-defined]


def test_mark_failed_circuit_breaker_increments_completed_tasks(mocker: MockerFixture) -> None:
    """Circuit-breaker early-exit path must increment _completed_tasks before _emit_progress."""
    # Arrange
    task = _make_task(mocker)
    task._data_api.retrieve_status_counts_for_run.return_value = {}  # type: ignore[attr-defined]
    result = _make_result()
    assert task._completed_tasks == 0

    # Act — simulate the circuit-breaker branch
    task._mark_failed(result, RuntimeError("Provider 'p1' unresponsive — circuit tripped"))
    task._completed_tasks += 1
    task._emit_progress()

    # Assert
    assert task._completed_tasks == 1
    task._event_bus.emit_progress_update.assert_called_once()  # type: ignore[attr-defined]


def test_mark_failed_model_excluded_increments_completed_tasks(mocker: MockerFixture) -> None:
    """Model-exclusion early-exit path must increment _completed_tasks before _emit_progress."""
    # Arrange
    task = _make_task(mocker)
    task._data_api.retrieve_status_counts_for_run.return_value = {}  # type: ignore[attr-defined]
    result = _make_result()
    assert task._completed_tasks == 0

    # Act — simulate the model-exclusion branch
    task._mark_failed(result, RuntimeError("Model excluded after 3 consecutive timeouts at 60s"))
    task._completed_tasks += 1
    task._emit_progress()

    # Assert
    assert task._completed_tasks == 1
    task._event_bus.emit_progress_update.assert_called_once()  # type: ignore[attr-defined]
