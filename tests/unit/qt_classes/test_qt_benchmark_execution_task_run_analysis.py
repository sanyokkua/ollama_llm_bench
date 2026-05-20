"""Unit tests for run-level analysis routing in BenchmarkExecutionTask.

Tests verify that _stage_run_analysis is called (or not) based on the
judge_run_analysis_enabled app setting, and that the method behaves
correctly for each run mode.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

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
    LogFileWriterApi,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunStatus,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
    ResponseScope,
    RunMode,
    TaskType,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    _DEFAULTS,
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
    SETTING_RETRY_COUNT,
)
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask


@dataclass
class ExecTaskFixture:
    task: BenchmarkExecutionTask
    data_api: MagicMock
    task_loader: MagicMock
    judge_summary_service: MagicMock
    event_bus: MagicMock
    app_settings: MagicMock


def _make_run(
    *,
    run_mode: RunMode = RunMode.PERFORMANCE,
    judge_provider_id: str = "ollama",
    judge_model: str = "qwen3:8b",
) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model=judge_model,
        judge_provider_id=judge_provider_id,
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=run_mode,
        models_json='[{"provider_id":"p1","provider_type":"openai_compatible","model_name":"m1","display_label":"m1"}]',
        task_file_paths=("tasks/test.yaml",),
    )


def _make_exec_task(mocker: MockerFixture) -> ExecTaskFixture:
    app_settings = mocker.MagicMock(spec=AppSettingsServiceApi)
    app_settings.get_bool.return_value = False
    app_settings.get_int.side_effect = lambda key, default=0: int(_DEFAULTS.get(key, str(default)))
    data_api = mocker.MagicMock(spec=DataApi)
    task_loader = mocker.MagicMock(spec=TaskFileLoaderApi)
    judge_summary_service = mocker.MagicMock(spec=JudgeSummaryServiceApi)
    event_bus = mocker.MagicMock(spec=EventBus)
    rule_evaluator = mocker.MagicMock(spec=EvaluatorApi)
    keyword_evaluator = mocker.MagicMock(spec=EvaluatorApi)
    cosine_evaluator = mocker.MagicMock(spec=EvaluatorApi)
    llm_judge_evaluator = mocker.MagicMock(spec=LLMJudgeEvaluatorApi)
    task = BenchmarkExecutionTask(
        run_id=1,
        data_api=data_api,
        task_loader=task_loader,
        judge_prompt_service=mocker.MagicMock(spec=JudgePromptServiceApi),
        judge_summary_service=judge_summary_service,
        provider_registry=mocker.MagicMock(spec=ProviderRegistryApi),
        event_bus=event_bus,
        app_settings=app_settings,
        rule_evaluator=rule_evaluator,
        keyword_evaluator=keyword_evaluator,
        cosine_evaluator=cosine_evaluator,
        llm_judge_evaluator=llm_judge_evaluator,
        log_file_writer=mocker.MagicMock(spec=LogFileWriterApi),
    )
    task.signals = mocker.MagicMock()
    rule_evaluator.layer = EvalLayer.RULE_BASED
    keyword_evaluator.layer = EvalLayer.KEYWORD
    cosine_evaluator.layer = EvalLayer.COSINE
    llm_judge_evaluator.layer = EvalLayer.LLM_JUDGE
    return ExecTaskFixture(
        task=task,
        data_api=data_api,
        task_loader=task_loader,
        judge_summary_service=judge_summary_service,
        event_bus=event_bus,
        app_settings=app_settings,
    )


def _set_flag(app_settings: MagicMock, flag_key: str, value: bool) -> None:
    """Override get_bool so only flag_key returns value; all others return False."""

    def _side_effect(key: str, default: bool = False) -> bool:
        if key == flag_key:
            return value
        return False

    app_settings.get_bool.side_effect = _side_effect


class TestRunAnalysisRouting:
    def test_flag_on_calls_stage_run_analysis(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="ollama", judge_model="qwen3:8b")
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.task_loader.load_tasks.return_value = []

        _set_flag(fx.app_settings, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        fx.task.run()

        analysis_spy.assert_called_once_with(run)

    def test_flag_off_does_not_call_stage_run_analysis(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="ollama", judge_model="qwen3:8b")
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        fx.task.run()

        analysis_spy.assert_not_called()

    def test_flag_on_full_grading_calls_stage_run_analysis(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []

        _set_flag(fx.app_settings, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_stage_judging")
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        fx.task.run()

        analysis_spy.assert_called_once_with(run)

    def test_flag_off_full_grading_does_not_call_stage_run_analysis(self, mocker: MockerFixture) -> None:
        """Flag gates analysis for ALL modes including FULL_GRADING."""
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_stage_judging")
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        fx.task.run()

        analysis_spy.assert_not_called()

    def test_stage_run_analysis_no_judge_emits_warning(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="", judge_model="")

        warn_spy = mocker.patch.object(fx.task, "_notify_warn")
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []

        fx.task._stage_run_analysis(run)

        calls = [str(c) for c in warn_spy.call_args_list]
        assert any("skipped" in c.lower() or "judge" in c.lower() for c in calls)

    def test_stage_run_analysis_full_grading_emits_judge_summary(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.judge_summary_service.generate_summary.return_value = "analysis text"

        fx.task._stage_run_analysis(run)

        fx.event_bus.emit_judge_summary.assert_called_once()
        fx.event_bus.emit_perf_analysis.assert_not_called()

    def test_stage_run_analysis_performance_emits_perf_analysis(self, mocker: MockerFixture) -> None:
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE)
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.judge_summary_service.generate_summary.return_value = "perf text"

        fx.task._stage_run_analysis(run)

        fx.event_bus.emit_perf_analysis.assert_called_once()
        fx.event_bus.emit_judge_summary.assert_not_called()

    def test_stage_run_analysis_speed_emits_perf_analysis(self, mocker: MockerFixture) -> None:
        # Arrange
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.judge_summary_service.generate_summary.return_value = "speed perf text"

        # Act
        fx.task._stage_run_analysis(run)

        # Assert
        fx.event_bus.emit_perf_analysis.assert_called_once()
        fx.event_bus.emit_judge_summary.assert_not_called()

    def test_stage_run_analysis_prompt_eval_emits_perf_analysis(self, mocker: MockerFixture) -> None:
        # Arrange
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.judge_summary_service.generate_summary.return_value = "prompt eval perf text"

        # Act
        fx.task._stage_run_analysis(run)

        # Assert
        fx.event_bus.emit_perf_analysis.assert_called_once()
        fx.event_bus.emit_judge_summary.assert_not_called()

    def test_flag_on_speed_calls_stage_run_analysis(self, mocker: MockerFixture) -> None:
        # Arrange
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED, judge_provider_id="ollama", judge_model="qwen3:8b")
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []
        fx.task_loader.load_tasks.return_value = []

        _set_flag(fx.app_settings, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        # Act
        fx.task.run()

        # Assert
        analysis_spy.assert_called_once_with(run)

    def test_flag_on_prompt_eval_calls_stage_run_analysis(self, mocker: MockerFixture) -> None:
        # Arrange
        fx = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PROMPT_EVAL, judge_provider_id="ollama", judge_model="qwen3:8b")
        fx.data_api.retrieve_benchmark_run.return_value = run
        fx.data_api.retrieve_benchmark_results_for_run.return_value = []

        _set_flag(fx.app_settings, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        analysis_spy = mocker.patch.object(fx.task, "_stage_run_analysis")
        mocker.patch.object(fx.task, "_stage_initializing", return_value={})
        mocker.patch.object(fx.task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(fx.task, "_stage_judging")
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)

        # Act
        fx.task.run()

        # Assert
        analysis_spy.assert_called_once_with(run)

    def test_eval_pipeline_renamed_params_accepted(self, mocker: MockerFixture) -> None:
        """Ensure _run_eval_pipeline accepts the renamed judge_override_* keyword params."""
        fx = _make_exec_task(mocker)
        run = _make_run()
        result = BenchmarkResult(
            run_id=1,
            task_id="t1",
            provider_id="p1",
            model_name="m1",
        )
        task_obj = BenchmarkTask(
            task_id="t1",
            category="math",
            sub_category="arithmetic",
            task_type=TaskType.FACTUAL_QA,
            question="Q?",
            golden_answer="A",
            pass_criteria="must contain the answer",  # noqa: S106  # Not a password — task eval criterion
            fail_criteria="must not be wrong",
            difficulty=Difficulty.EASY,
            response_scope=ResponseScope.CONTAINS,
        )

        # This must not raise TypeError due to old param names (force_keyword / force_cosine)
        try:
            fx.task._run_eval_pipeline(
                task=task_obj,
                result=result,
                run=run,
                judge_override_keyword_fail=False,
                judge_override_cosine_low=False,
            )
        except TypeError as exc:
            pytest.fail(f"Renamed params rejected: {exc}")


def _make_evaluation_result(*, verdict: EvalVerdict, is_terminal: bool) -> EvaluationResult:
    return EvaluationResult(
        verdict=verdict,
        score=0.9 if verdict == EvalVerdict.PASS else 0.0,
        reasoning="test reasoning",
        is_terminal=is_terminal,
        layer=EvalLayer.LLM_JUDGE,
    )


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        category="cat",
        sub_category="sub",
        task_type=TaskType.FACTUAL_QA,
        question="Q?",
        golden_answer="A",
        pass_criteria="correct",  # noqa: S106
        fail_criteria="wrong",
        difficulty=Difficulty.EASY,
        response_scope=ResponseScope.CONTAINS,
    )


def _make_result() -> BenchmarkResult:
    return BenchmarkResult(
        run_id=1,
        task_id="t1",
        provider_id="p1",
        model_name="m1",
    )


class TestJudgeRetryOnUnknown:
    """_run_judge_with_retry retries when a non-terminal UNKNOWN is returned."""

    def _make_task_with_retry_count(
        self, mocker: MockerFixture, retry_count: int
    ) -> tuple[BenchmarkExecutionTask, MagicMock]:
        from ollama_llm_bench.backend.services.adaptive_timeout_service import AdaptiveTimeoutService

        fx = _make_exec_task(mocker)

        def _get_int_side_effect(key: str, default: int = 0) -> int:
            if key == SETTING_RETRY_COUNT:
                return retry_count
            return int(_DEFAULTS.get(key, str(default)))

        fx.app_settings.get_int.side_effect = _get_int_side_effect
        mocker.patch.object(fx.task, "_check_pause_or_stop", return_value=True)
        mocker.patch.object(fx.task, "_on_task_timeout")
        mocker.patch.object(fx.task, "_notify_warn")
        mock_timeout = mocker.MagicMock(spec=AdaptiveTimeoutService)
        mock_timeout.next_timeout.return_value = 300
        fx.task._adaptive_timeout = mock_timeout
        return fx.task, mock_timeout

    def test_retries_once_on_non_terminal_unknown(self, mocker: MockerFixture) -> None:
        """evaluate() called twice: first UNKNOWN non-terminal, then PASS terminal."""
        task, _ = self._make_task_with_retry_count(mocker, retry_count=2)
        run = _make_run()
        judge_eval = mocker.MagicMock(spec=LLMJudgeEvaluatorApi)
        judge_eval.evaluate.side_effect = [
            _make_evaluation_result(verdict=EvalVerdict.UNKNOWN, is_terminal=False),
            _make_evaluation_result(verdict=EvalVerdict.PASS, is_terminal=True),
        ]

        result = task._run_judge_with_retry(judge_eval, _make_task(), _make_result(), run)

        assert judge_eval.evaluate.call_count == 2
        assert result.verdict == EvalVerdict.PASS
        assert result.is_terminal is True

    def test_record_success_called_after_terminal_result(self, mocker: MockerFixture) -> None:
        """record_success is called once, after the terminal PASS on the second attempt."""
        task, mock_timeout = self._make_task_with_retry_count(mocker, retry_count=2)
        run = _make_run()
        judge_eval = mocker.MagicMock(spec=LLMJudgeEvaluatorApi)
        judge_eval.evaluate.side_effect = [
            _make_evaluation_result(verdict=EvalVerdict.UNKNOWN, is_terminal=False),
            _make_evaluation_result(verdict=EvalVerdict.PASS, is_terminal=True),
        ]

        task._run_judge_with_retry(judge_eval, _make_task(), _make_result(), run)

        mock_timeout.record_success.assert_called_once()

    def test_no_retry_when_retry_count_is_one(self, mocker: MockerFixture) -> None:
        """With retry_count=1 there is no second attempt — UNKNOWN is returned as-is."""
        task, mock_timeout = self._make_task_with_retry_count(mocker, retry_count=1)
        run = _make_run()
        judge_eval = mocker.MagicMock(spec=LLMJudgeEvaluatorApi)
        unknown_result = _make_evaluation_result(verdict=EvalVerdict.UNKNOWN, is_terminal=False)
        judge_eval.evaluate.return_value = unknown_result

        result = task._run_judge_with_retry(judge_eval, _make_task(), _make_result(), run)

        assert judge_eval.evaluate.call_count == 1
        assert result.verdict == EvalVerdict.UNKNOWN
        mock_timeout.record_success.assert_called_once()
