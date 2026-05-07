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
    task = BenchmarkExecutionTask(
        run_id=1,
        data_api=mocker.Mock(spec=DataApi),
        task_loader=mocker.Mock(spec=TaskFileLoaderApi),
        judge_prompt_service=mocker.Mock(spec=JudgePromptServiceApi),
        judge_summary_service=mocker.Mock(spec=JudgeSummaryServiceApi),
        provider_registry=mocker.Mock(spec=ProviderRegistryApi),
        event_bus=mocker.Mock(spec=EventBus),
        app_settings=mocker.Mock(spec=AppSettingsServiceApi),
        rule_evaluator=mocker.Mock(spec=EvaluatorApi),
        keyword_evaluator=mocker.Mock(spec=EvaluatorApi),
        cosine_evaluator=mocker.Mock(spec=EvaluatorApi),
        llm_judge_evaluator=mocker.Mock(spec=LLMJudgeEvaluatorApi),
        log_file_writer=mocker.Mock(spec=LogFileWriterApi),
    )
    task._pause_event.set()
    return task


# ---------------------------------------------------------------------------
# _calc_attempt_timeout tests
# ---------------------------------------------------------------------------


def test_calc_attempt_timeout_single_attempt_returns_min() -> None:
    result = BenchmarkExecutionTask._calc_attempt_timeout(30, 300, 0, 1)
    assert result == 30


def test_calc_attempt_timeout_first_attempt_is_min() -> None:
    result = BenchmarkExecutionTask._calc_attempt_timeout(30, 300, 0, 3)
    assert result == 30


def test_calc_attempt_timeout_last_attempt_is_max() -> None:
    result = BenchmarkExecutionTask._calc_attempt_timeout(30, 300, 2, 3)
    assert result == 300


def test_calc_attempt_timeout_middle_is_geometric() -> None:
    min_s, max_s = 30, 300
    mid = BenchmarkExecutionTask._calc_attempt_timeout(min_s, max_s, 1, 3)
    expected = round(min_s * (max_s / min_s) ** 0.5)
    assert mid == expected
    assert min_s < mid < max_s


def test_calc_attempt_timeout_equal_min_max_returns_min() -> None:
    result = BenchmarkExecutionTask._calc_attempt_timeout(120, 120, 1, 3)
    assert result == 120


def test_calc_attempt_timeout_clamps_to_range() -> None:
    # With min > max (misconfiguration), result should clamp to min
    result = BenchmarkExecutionTask._calc_attempt_timeout(300, 30, 0, 1)
    assert result == 300  # min_s is returned for single attempt regardless of max


# ---------------------------------------------------------------------------
# _run_inference_with_retry tests
# ---------------------------------------------------------------------------


def test_run_inference_with_retry_succeeds_on_first_attempt(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)

    exec_task._app_settings.get_int.side_effect = lambda key, default=0: {
        SETTING_RETRY_COUNT: 3,
        SETTING_RETRY_TIMEOUT_MIN_S: 30,
        SETTING_RETRY_TIMEOUT_MAX_S: 300,
    }.get(key, default)

    updated_result = _make_result()
    exec_task._run_inference = mocker.Mock(return_value=updated_result)  # type: ignore[method-assign]

    returned = exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)

    assert returned is updated_result
    assert exec_task._run_inference.call_count == 1


def test_run_inference_with_retry_succeeds_on_second_attempt(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)

    exec_task._app_settings.get_int.side_effect = lambda key, default=0: {
        SETTING_RETRY_COUNT: 3,
        SETTING_RETRY_TIMEOUT_MIN_S: 30,
        SETTING_RETRY_TIMEOUT_MAX_S: 300,
    }.get(key, default)

    updated_result = _make_result()
    call_count = 0

    def _fake_inference(*_args: object, **_kwargs: object) -> BenchmarkResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exec_task._attempt_timed_out = True
        return updated_result

    exec_task._run_inference = _fake_inference  # type: ignore[method-assign]

    returned = exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)

    assert returned is updated_result
    assert call_count == 2


def test_run_inference_with_retry_fails_after_all_retries(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)

    exec_task._app_settings.get_int.side_effect = lambda key, default=0: {
        SETTING_RETRY_COUNT: 3,
        SETTING_RETRY_TIMEOUT_MIN_S: 30,
        SETTING_RETRY_TIMEOUT_MAX_S: 300,
    }.get(key, default)

    def _always_timeout(*_args: object, **_kwargs: object) -> BenchmarkResult:
        exec_task._attempt_timed_out = True
        return _make_result()

    exec_task._run_inference = _always_timeout  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="timed out after 3 attempt"):
        exec_task._run_inference_with_retry(provider, "m1", result, task, BenchmarkResultStatus.COMPLETED)


def test_run_inference_with_retry_stops_when_stop_requested(mocker: MockerFixture) -> None:
    exec_task = _make_exec_task(mocker)
    task = _make_task()
    result = _make_result()
    provider = mocker.Mock(spec=LLMProviderApi)

    exec_task._app_settings.get_int.side_effect = lambda key, default=0: {
        SETTING_RETRY_COUNT: 3,
        SETTING_RETRY_TIMEOUT_MIN_S: 30,
        SETTING_RETRY_TIMEOUT_MAX_S: 300,
    }.get(key, default)

    # Simulate stop being requested before the first attempt
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
