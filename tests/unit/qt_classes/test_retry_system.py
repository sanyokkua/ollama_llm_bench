"""Unit tests for the exponential retry system in BenchmarkExecutionTask."""

import json
import logging

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EvaluatorApi,
    EventBus,
    JudgePromptServiceApi,
    JudgeSummaryServiceApi,
    LLMJudgeEvaluatorApi,
    LLMProviderApi,
    LogFileWriterApi,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkTask,
    Difficulty,
    ResponseScope,
    TaskType,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_RETRY_COUNT,
    SETTING_RETRY_MAX_FAILURES_TO_EXCLUDE,
    SETTING_RETRY_TIMEOUT_MAX_S,
    SETTING_RETRY_TIMEOUT_MIN_S,
)
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_task(task_id: str = "t1") -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        category="math",
        sub_category="arithmetic",
        task_type=TaskType.FACTUAL_QA,
        question="What is 2+2?",
        golden_answer="4",
        pass_criteria="must be correct",  # noqa: S106
        fail_criteria="must not be wrong",
        difficulty=Difficulty.EASY,
        response_scope=ResponseScope.CONTAINS,
    )


def _make_result(task_id: str = "t1") -> BenchmarkResult:
    return BenchmarkResult(
        run_id=1,
        task_id=task_id,
        provider_id="p1",
        model_name="m1",
        status=BenchmarkResultStatus.NOT_COMPLETED,
        user_prompt_sent="",
    )


def _make_exec_task(mocker: MockerFixture) -> BenchmarkExecutionTask:
    app_settings = mocker.Mock(spec=AppSettingsServiceApi)
    # Return 1 for all int settings so AdaptiveTimeoutService init does not fail.
    # Individual tests may override side_effect to return specific values.
    app_settings.get_int.return_value = 1
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
    task._pause_event.set()
    return task


# ---------------------------------------------------------------------------
# _run_inference_with_retry tests
# ---------------------------------------------------------------------------


def _patch_get_int(mocker: MockerFixture, exec_task: BenchmarkExecutionTask) -> None:
    """Patch app_settings.get_int with retry-specific values."""
    mocker.patch.object(
        exec_task._app_settings,
        "get_int",
        side_effect=lambda key, default=0: {
            SETTING_RETRY_COUNT: 3,
            SETTING_RETRY_TIMEOUT_MIN_S: 30,
            SETTING_RETRY_TIMEOUT_MAX_S: 300,
            SETTING_RETRY_MAX_FAILURES_TO_EXCLUDE: 3,
        }.get(key, default),
    )


def test_run_inference_with_retry_succeeds_on_first_attempt(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)
    _patch_get_int(mocker, exec_task)

    updated_result = _make_result()
    inference_mock = mocker.patch.object(exec_task, "_run_inference", return_value=updated_result)

    returned = exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)

    assert returned is updated_result
    assert inference_mock.call_count == 1


def test_run_inference_with_retry_succeeds_on_second_attempt(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)
    _patch_get_int(mocker, exec_task)

    updated_result = _make_result()
    call_count = 0

    def _fake_inference(*_args: object, **_kwargs: object) -> BenchmarkResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exec_task._attempt_timed_out = True
        return updated_result

    mocker.patch.object(exec_task, "_run_inference", side_effect=_fake_inference)

    returned = exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)

    assert returned is updated_result
    assert call_count == 2


def test_run_inference_with_retry_fails_after_all_retries(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)
    _patch_get_int(mocker, exec_task)

    def _always_timeout(*_args: object, **_kwargs: object) -> BenchmarkResult:
        exec_task._attempt_timed_out = True
        return _make_result()

    mocker.patch.object(exec_task, "_run_inference", side_effect=_always_timeout)

    with pytest.raises(TimeoutError, match="timed out after 3 attempt"):
        exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)


def test_run_inference_with_retry_stops_when_stop_requested(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)
    _patch_get_int(mocker, exec_task)

    exec_task._stop_requested = True

    with pytest.raises(StopIteration):
        exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)


# ---------------------------------------------------------------------------
# Settings defaults / serialization
# ---------------------------------------------------------------------------


def test_retry_setting_constants_have_expected_names() -> None:
    assert SETTING_RETRY_COUNT == "benchmark.retry_count"
    assert SETTING_RETRY_TIMEOUT_MIN_S == "benchmark.retry_timeout_min_s"
    assert SETTING_RETRY_TIMEOUT_MAX_S == "benchmark.retry_timeout_max_s"


# ---------------------------------------------------------------------------
# _parse_model_descriptors tests
# ---------------------------------------------------------------------------


def test_parse_model_descriptors_valid_entry_returns_list() -> None:
    entry = {
        "provider_id": "ollama_local",
        "provider_type": "openai_compatible",
        "model_name": "llama3.2:3b",
        "display_label": "LLaMA 3.2 3B",
    }
    result = BenchmarkExecutionTask._parse_model_descriptors(json.dumps([entry]))
    assert len(result) == 1
    assert result[0].provider_id == "ollama_local"
    assert result[0].model_name == "llama3.2:3b"


def test_parse_model_descriptors_missing_required_key_skips_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = {"provider_type": "openai_compatible", "model_name": "llama3.2:3b"}
    with caplog.at_level(logging.WARNING):
        result = BenchmarkExecutionTask._parse_model_descriptors(json.dumps([entry]))
    assert result == []
    assert any("malformed_model_descriptor" in r.message for r in caplog.records)


def test_parse_model_descriptors_invalid_json_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = BenchmarkExecutionTask._parse_model_descriptors("not valid json {{")
    assert result == []
    assert any("models_json_parse_failed" in r.message for r in caplog.records)


def test_parse_model_descriptors_empty_array_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = BenchmarkExecutionTask._parse_model_descriptors("[]")
    assert result == []
    assert len(caplog.records) == 0
