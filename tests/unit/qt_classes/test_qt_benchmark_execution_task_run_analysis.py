"""Unit tests for run-level analysis routing in BenchmarkExecutionTask.

Tests verify that _stage_performance_analysis and _generate_and_emit_judge_summary
are called in the correct cases based on run mode and judge_run_analysis_enabled
app setting.
"""

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
    BenchmarkRun,
    BenchmarkRunStatus,
    EvalLayer,
    RunMode,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    _DEFAULTS,
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
)
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask


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
    task.signals = mocker.Mock()
    task._app_settings.get_bool.return_value = False  # type: ignore[attr-defined]
    task._app_settings.get_int.side_effect = lambda key, default=0: int(  # type: ignore[attr-defined]
        _DEFAULTS.get(key, str(default))
    )
    task._rule_evaluator.layer = EvalLayer.RULE_BASED  # type: ignore[misc]
    task._keyword_evaluator.layer = EvalLayer.KEYWORD  # type: ignore[misc]
    task._cosine_evaluator.layer = EvalLayer.COSINE  # type: ignore[misc]
    task._llm_judge_evaluator.layer = EvalLayer.LLM_JUDGE  # type: ignore[misc]
    return task


def _set_flag(task: BenchmarkExecutionTask, flag_key: str, value: bool) -> None:
    """Override get_bool so only flag_key returns value; all others return False."""

    def _side_effect(key: str, default: bool = False) -> bool:
        if key == flag_key:
            return value
        return False

    task._app_settings.get_bool.side_effect = _side_effect  # type: ignore[attr-defined]


class TestRunAnalysisRouting:
    def test_performance_flag_on_with_judge_calls_stage_performance_analysis(self, mocker: MockerFixture) -> None:
        task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="ollama", judge_model="qwen3:8b")
        task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        task._task_loader.load_tasks.return_value = []  # type: ignore[attr-defined]

        _set_flag(task, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        perf_spy = mocker.patch.object(task, "_stage_performance_analysis")
        judge_spy = mocker.patch.object(task, "_generate_and_emit_judge_summary")
        mocker.patch.object(task, "_stage_initializing", return_value={})
        mocker.patch.object(task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(task, "_check_pause_or_stop", return_value=True)

        task.run()

        perf_spy.assert_called_once_with(run)
        judge_spy.assert_not_called()

    def test_performance_flag_on_no_judge_emits_warning_not_analysis(self, mocker: MockerFixture) -> None:
        task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="", judge_model="")
        task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]

        _set_flag(task, SETTING_JUDGE_RUN_ANALYSIS_ENABLED, True)

        perf_spy = mocker.patch.object(task, "_stage_performance_analysis")
        warn_spy = mocker.patch.object(task, "_notify_warn")
        mocker.patch.object(task, "_stage_initializing", return_value={})
        mocker.patch.object(task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(task, "_check_pause_or_stop", return_value=True)

        task.run()

        perf_spy.assert_not_called()
        calls = [str(c) for c in warn_spy.call_args_list]
        assert any("skipped" in c.lower() or "judge" in c.lower() for c in calls)

    def test_performance_flag_off_does_not_call_performance_analysis(self, mocker: MockerFixture) -> None:
        task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PERFORMANCE, judge_provider_id="ollama", judge_model="qwen3:8b")
        task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]

        # flag stays False (default)
        perf_spy = mocker.patch.object(task, "_stage_performance_analysis")
        mocker.patch.object(task, "_stage_initializing", return_value={})
        mocker.patch.object(task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(task, "_check_pause_or_stop", return_value=True)

        task.run()

        perf_spy.assert_not_called()

    def test_full_grading_calls_generate_judge_summary_when_flag_off(self, mocker: MockerFixture) -> None:
        task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]

        # flag stays False (default)
        judge_spy = mocker.patch.object(task, "_generate_and_emit_judge_summary")
        perf_spy = mocker.patch.object(task, "_stage_performance_analysis")
        mocker.patch.object(task, "_stage_initializing", return_value={})
        mocker.patch.object(task, "_stage_benchmarking", return_value=True)
        mocker.patch.object(task, "_stage_judging")
        mocker.patch.object(task, "_check_pause_or_stop", return_value=True)

        task.run()

        judge_spy.assert_called_once_with(run)
        perf_spy.assert_not_called()

    def test_eval_pipeline_renamed_params_accepted(self, mocker: MockerFixture) -> None:
        """Ensure _run_eval_pipeline accepts the renamed judge_override_* keyword params."""
        task = _make_exec_task(mocker)
        from ollama_llm_bench.backend.core.models import (
            BenchmarkResult,
            BenchmarkTask,
            Difficulty,
            ResponseScope,
            TaskType,
        )

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
            task._run_eval_pipeline(
                task=task_obj,
                result=result,
                run=run,
                judge_override_keyword_fail=False,
                judge_override_cosine_low=False,
            )
        except TypeError as exc:
            pytest.fail(f"Renamed params rejected: {exc}")
