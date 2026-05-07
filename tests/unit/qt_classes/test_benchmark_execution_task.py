"""Unit tests for BenchmarkExecutionTask — pipeline orchestration, field initialisation, and prompt eval mode."""

import dataclasses

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
    BenchmarkRun,
    BenchmarkRunStatus,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
    InferenceResponse,
    ModelDescriptor,
    PromptVariant,
    ProviderType,
    ResponseScope,
    RunMode,
    TaskType,
)
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

_MODELS_JSON = '[{"provider_id":"p1","provider_type":"openai_compatible","model_name":"m1","display_label":"m1"}]'


def _make_run(
    *,
    run_mode: RunMode = RunMode.FULL_GRADING,
    models_json: str = _MODELS_JSON,
) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model="qwen3:8b",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=run_mode,
        models_json=models_json,
        task_file_paths=("tasks/test.yaml",),
    )


def _make_task(
    task_id: str = "t1",
    *,
    question: str = "What is 2+2?",
    source_language: str | None = None,
    target_language: str | None = None,
) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        category="math",
        sub_category="arithmetic",
        task_type=TaskType.FACTUAL_QA,
        question=question,
        golden_answer="4",
        pass_criteria="must be correct",  # noqa: S106  # Not a password — task evaluation criterion
        fail_criteria="must not be wrong",
        difficulty=Difficulty.EASY,
        response_scope=ResponseScope.CONTAINS,
        source_language=source_language,
        target_language=target_language,
    )


def _make_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="p1",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        model_name="m1",
        display_label="m1",
    )


def _make_result(
    *,
    task_id: str = "t1",
    status: BenchmarkResultStatus = BenchmarkResultStatus.NOT_COMPLETED,
    user_prompt_sent: str = "",
    system_prompt_sent: str | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=1,
        task_id=task_id,
        provider_id="p1",
        model_name="m1",
        status=status,
        user_prompt_sent=user_prompt_sent,
        system_prompt_sent=system_prompt_sent,
    )


def _make_variant(
    variant_id: str = "var_a",
    *,
    template: str = "Answer this: {question}",
    system_prompt: str | None = None,
) -> PromptVariant:
    return PromptVariant(
        variant_id=variant_id,
        run_id=1,
        variant_label=f"Variant {variant_id}",
        user_prompt_template=template,
        created_at="2026-01-01T00:00:00",
        system_prompt=system_prompt,
    )


def _make_inference_response(*, llm_response: str = "plain answer") -> InferenceResponse:
    return InferenceResponse(
        llm_response=llm_response,
        total_time_ms=100,
        completion_tokens=10,
    )


def _non_terminal_unknown(layer: EvalLayer) -> EvaluationResult:
    return EvaluationResult(
        verdict=EvalVerdict.UNKNOWN,
        score=0.5,
        reasoning="",
        is_terminal=False,
        layer=layer,
    )


def _make_exec_task(mocker: MockerFixture) -> BenchmarkExecutionTask:
    """Build a BenchmarkExecutionTask with all dependencies mocked."""
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
    # Replace Qt QObject-based Signals with a plain mock so no QApplication is needed
    task.signals = mocker.Mock()
    # All feature flags disabled — ensures sync inference path is taken in _run_inference tests
    task._app_settings.get_bool.return_value = False  # type: ignore[attr-defined]
    # Return sensible defaults for integer settings keyed from _DEFAULTS
    from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

    task._app_settings.get_int.side_effect = lambda key, default=0: int(  # type: ignore[attr-defined]
        _DEFAULTS.get(key, str(default))
    )
    # Wire evaluator layers
    task._rule_evaluator.layer = EvalLayer.RULE_BASED  # type: ignore[misc]
    task._keyword_evaluator.layer = EvalLayer.KEYWORD  # type: ignore[misc]
    task._cosine_evaluator.layer = EvalLayer.COSINE  # type: ignore[misc]
    task._llm_judge_evaluator.layer = EvalLayer.LLM_JUDGE  # type: ignore[misc]
    return task


# ---------------------------------------------------------------------------
# Tests — _build_initial_result (static method)
# ---------------------------------------------------------------------------


class TestBuildInitialResult:
    def test_sets_run_type(self) -> None:
        # Arrange
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        desc = _make_descriptor()
        task = _make_task()

        # Act
        result = BenchmarkExecutionTask._build_initial_result(run, desc, task)

        # Assert
        assert result.run_type == "full_grading"

    def test_copies_language_fields(self) -> None:
        # Arrange
        run = _make_run()
        desc = _make_descriptor()
        task = _make_task(source_language="en", target_language="fr")

        # Act
        result = BenchmarkExecutionTask._build_initial_result(run, desc, task)

        # Assert
        assert result.source_language == "en"
        assert result.target_language == "fr"

    def test_status_is_not_completed(self) -> None:
        run = _make_run()
        desc = _make_descriptor()
        task = _make_task()

        result = BenchmarkExecutionTask._build_initial_result(run, desc, task)

        assert result.status == BenchmarkResultStatus.NOT_COMPLETED


# ---------------------------------------------------------------------------
# Tests — _build_prompt_eval_result (static method)
# ---------------------------------------------------------------------------


class TestBuildPromptEvalResult:
    def test_pre_renders_user_prompt(self) -> None:
        # Arrange
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        desc = _make_descriptor()
        task = _make_task(question="What is 2+2?")
        variant = _make_variant(template="Please answer: {question}")

        # Act
        result = BenchmarkExecutionTask._build_prompt_eval_result(run, desc, task, variant)

        # Assert
        assert result.user_prompt_sent == "Please answer: What is 2+2?"

    def test_sets_prompt_version_to_variant_id(self) -> None:
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        desc = _make_descriptor()
        task = _make_task()
        variant = _make_variant(variant_id="var_b")

        result = BenchmarkExecutionTask._build_prompt_eval_result(run, desc, task, variant)

        assert result.prompt_version == "var_b"

    def test_copies_system_prompt(self) -> None:
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        desc = _make_descriptor()
        task = _make_task()
        variant = _make_variant(system_prompt="Be concise.")

        result = BenchmarkExecutionTask._build_prompt_eval_result(run, desc, task, variant)

        assert result.system_prompt_sent == "Be concise."

    def test_system_prompt_none_when_variant_has_none(self) -> None:
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        desc = _make_descriptor()
        task = _make_task()
        variant = _make_variant(system_prompt=None)

        result = BenchmarkExecutionTask._build_prompt_eval_result(run, desc, task, variant)

        assert result.system_prompt_sent is None


# ---------------------------------------------------------------------------
# Tests — _run_inference
# ---------------------------------------------------------------------------


class TestRunInference:
    def test_detects_thinking_block(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]
        provider = mocker.Mock(spec=LLMProviderApi)
        provider.inference_sync.return_value = _make_inference_response(llm_response="<think>reasoning</think>answer")
        result = _make_result()
        task = _make_task()

        # Act
        updated = exec_task._run_inference(provider, "m1", result, task, BenchmarkResultStatus.WAITING_FOR_JUDGE)

        # Assert
        assert updated.has_thinking_block is True
        assert updated.sanitized_response == "answer"

    def test_no_thinking_block_when_absent(self, mocker: MockerFixture) -> None:
        exec_task = _make_exec_task(mocker)
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]
        provider = mocker.Mock(spec=LLMProviderApi)
        provider.inference_sync.return_value = _make_inference_response(llm_response="plain answer")
        result = _make_result()
        task = _make_task()

        updated = exec_task._run_inference(provider, "m1", result, task, BenchmarkResultStatus.WAITING_FOR_JUDGE)

        assert updated.has_thinking_block is False

    def test_sets_prompt_hash(self, mocker: MockerFixture) -> None:
        exec_task = _make_exec_task(mocker)
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]
        provider = mocker.Mock(spec=LLMProviderApi)
        provider.inference_sync.return_value = _make_inference_response()
        result = _make_result()
        task = _make_task()

        updated = exec_task._run_inference(provider, "m1", result, task, BenchmarkResultStatus.WAITING_FOR_JUDGE)

        assert updated.prompt_hash.startswith("sha256:")
        assert len(updated.prompt_hash) == 71  # "sha256:" (7) + hex digest (64)

    def test_uses_prerendered_prompt_when_set(self, mocker: MockerFixture) -> None:
        # Arrange — result already has a pre-rendered prompt (prompt_eval row)
        exec_task = _make_exec_task(mocker)
        provider = mocker.Mock(spec=LLMProviderApi)
        provider.inference_sync.return_value = _make_inference_response()
        result = _make_result(user_prompt_sent="Pre-rendered prompt text")
        task = _make_task()

        # Act
        exec_task._run_inference(provider, "m1", result, task, BenchmarkResultStatus.WAITING_FOR_JUDGE)

        # Assert — judge prompt service must NOT be called
        exec_task._judge_prompt_service.build_inference_prompt.assert_not_called()  # type: ignore[attr-defined]

    def test_calls_service_when_no_prerendered_prompt(self, mocker: MockerFixture) -> None:
        exec_task = _make_exec_task(mocker)
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]
        provider = mocker.Mock(spec=LLMProviderApi)
        provider.inference_sync.return_value = _make_inference_response()
        result = _make_result(user_prompt_sent="")  # empty — no pre-render
        task = _make_task()

        exec_task._run_inference(provider, "m1", result, task, BenchmarkResultStatus.WAITING_FOR_JUDGE)

        exec_task._judge_prompt_service.build_inference_prompt.assert_called_once_with(task)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests — _stage_initializing_prompt_eval
# ---------------------------------------------------------------------------


class TestStageInitializingPromptEval:
    def test_creates_rows_per_variant(self, mocker: MockerFixture) -> None:
        # Arrange: 2 variants x 3 tasks = 6 rows
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        task_list = [_make_task(f"t{i}") for i in range(3)]
        descriptors = [_make_descriptor()]
        variants = [_make_variant("var_a"), _make_variant("var_b")]

        exec_task._data_api.retrieve_prompt_variants_for_run.return_value = variants  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = []  # type: ignore[attr-defined]

        # Act
        exec_task._stage_initializing_prompt_eval(run, task_list, descriptors)

        # Assert
        exec_task._data_api.create_benchmark_results.assert_called_once()  # type: ignore[attr-defined]
        created_rows: list[BenchmarkResult] = exec_task._data_api.create_benchmark_results.call_args[0][0]  # type: ignore[attr-defined]
        assert len(created_rows) == 6

    def test_no_variants_logs_warn_and_skips_creation(self, mocker: MockerFixture) -> None:
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        task_list = [_make_task()]
        descriptors = [_make_descriptor()]

        exec_task._data_api.retrieve_prompt_variants_for_run.return_value = []  # type: ignore[attr-defined]

        exec_task._stage_initializing_prompt_eval(run, task_list, descriptors)

        exec_task._data_api.create_benchmark_results.assert_not_called()  # type: ignore[attr-defined]

    def test_resumability_skips_existing_rows(self, mocker: MockerFixture) -> None:
        # Arrange: variant var_a / task t1 already exists — only 1 new row should be created
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.PROMPT_EVAL)
        task_list = [_make_task("t1")]
        descriptors = [_make_descriptor()]
        variants = [_make_variant("var_a"), _make_variant("var_b")]

        existing = [
            _make_result(task_id="t1", status=BenchmarkResultStatus.COMPLETED),
        ]
        # Simulate existing row with prompt_version "var_a"
        existing_with_version = [dataclasses.replace(existing[0], prompt_version="var_a")]
        exec_task._data_api.retrieve_prompt_variants_for_run.return_value = variants  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = existing_with_version  # type: ignore[attr-defined]

        exec_task._stage_initializing_prompt_eval(run, task_list, descriptors)

        created_rows: list[BenchmarkResult] = exec_task._data_api.create_benchmark_results.call_args[0][0]  # type: ignore[attr-defined]
        assert len(created_rows) == 1
        assert created_rows[0].prompt_version == "var_b"


# ---------------------------------------------------------------------------
# Tests — _mark_failed
# ---------------------------------------------------------------------------


class TestMarkFailed:
    def test_persists_inference_error(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        result = _make_result()
        error = RuntimeError("boom")

        # Act
        exec_task._mark_failed(result, error)

        # Assert
        exec_task._data_api.update_benchmark_result.assert_called_once()  # type: ignore[attr-defined]
        saved: BenchmarkResult = exec_task._data_api.update_benchmark_result.call_args[0][0]  # type: ignore[attr-defined]
        assert saved.has_inference_error is True
        assert "boom" in (saved.inference_error_message or "")
        assert saved.status == BenchmarkResultStatus.FAILED


# ---------------------------------------------------------------------------
# Tests — run() pipeline orchestration (end-to-end via direct call)
# ---------------------------------------------------------------------------


class TestRunPipelineOrchestration:
    def test_speed_mode_skips_judging_stage(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        result = _make_result(status=BenchmarkResultStatus.NOT_COMPLETED)
        task = _make_task()
        provider = mocker.Mock(spec=LLMProviderApi)

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = [result]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.return_value = [result]  # type: ignore[attr-defined]
        exec_task._provider_registry.get_provider.return_value = provider  # type: ignore[attr-defined]
        provider.inference_sync.return_value = _make_inference_response()
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]

        # Act
        exec_task.run()

        # Assert — WAITING_FOR_JUDGE must never appear as a queried status
        call_statuses = [
            call.kwargs.get("status")
            for call in exec_task._data_api.retrieve_benchmark_results_for_run_with_status.call_args_list  # type: ignore[attr-defined]
        ]
        assert BenchmarkResultStatus.WAITING_FOR_JUDGE not in call_statuses

    def test_full_grading_mode_runs_eval_pipeline(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.FULL_GRADING)
        result_pending = _make_result(status=BenchmarkResultStatus.NOT_COMPLETED)
        result_waiting = dataclasses.replace(result_pending, status=BenchmarkResultStatus.WAITING_FOR_JUDGE)
        task = _make_task()
        provider = mocker.Mock(spec=LLMProviderApi)

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._task_loader.get_task.return_value = task  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = [result_pending]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.side_effect = lambda *, run_id, status: (  # type: ignore[attr-defined]
            [result_pending] if status == BenchmarkResultStatus.NOT_COMPLETED else [result_waiting]
        )
        exec_task._provider_registry.get_provider.return_value = provider  # type: ignore[attr-defined]
        provider.inference_sync.return_value = _make_inference_response()
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]

        # Evaluators: layers 1-3 non-terminal UNKNOWN, LLM judge → terminal PASS
        exec_task._rule_evaluator.evaluate.return_value = _non_terminal_unknown(EvalLayer.RULE_BASED)  # type: ignore[attr-defined]
        exec_task._keyword_evaluator.evaluate.return_value = _non_terminal_unknown(EvalLayer.KEYWORD)  # type: ignore[attr-defined]
        exec_task._cosine_evaluator.evaluate.return_value = _non_terminal_unknown(EvalLayer.COSINE)  # type: ignore[attr-defined]
        exec_task._llm_judge_evaluator.evaluate.return_value = EvaluationResult(  # type: ignore[attr-defined]
            verdict=EvalVerdict.PASS,
            score=0.9,
            reasoning="Good answer",
            is_terminal=True,
            layer=EvalLayer.LLM_JUDGE,
        )

        # Act
        exec_task.run()

        # Assert — at least one update_benchmark_result call has status=COMPLETED
        saved_statuses = [
            call.args[0].status
            for call in exec_task._data_api.update_benchmark_result.call_args_list  # type: ignore[attr-defined]
            if call.args
        ]
        assert BenchmarkResultStatus.COMPLETED in saved_statuses

    def test_stop_cancels_before_benchmarking(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run()
        task = _make_task()

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = []  # type: ignore[attr-defined]

        # Act — stop() before run() so _check_pause_or_stop() returns False after init
        exec_task.stop()
        exec_task.run()

        # Assert — benchmarking stage never entered
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.assert_not_called()  # type: ignore[attr-defined]
        exec_task._event_bus.emit_benchmark_stopped.assert_called_once()  # type: ignore[attr-defined]

    def test_run_completion_persists_completed_status(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        result = _make_result(status=BenchmarkResultStatus.NOT_COMPLETED)
        task = _make_task()
        provider = mocker.Mock(spec=LLMProviderApi)

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = [result]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.return_value = [result]  # type: ignore[attr-defined]
        exec_task._provider_registry.get_provider.return_value = provider  # type: ignore[attr-defined]
        provider.inference_sync.return_value = _make_inference_response()
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]

        # Act
        exec_task.run()

        # Assert — update_benchmark_run called with COMPLETED status
        update_run_calls = exec_task._data_api.update_benchmark_run.call_args_list  # type: ignore[attr-defined]
        persisted_statuses = [c.args[0].status for c in update_run_calls if c.args]
        assert BenchmarkRunStatus.COMPLETED in persisted_statuses

    def test_run_failure_persists_failed_status(self, mocker: MockerFixture) -> None:
        # Arrange — make benchmarking raise so the pipeline enters FAILED state
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        result = _make_result(status=BenchmarkResultStatus.NOT_COMPLETED)
        task = _make_task()

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = [result]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.side_effect = RuntimeError("db error")  # type: ignore[attr-defined]

        # Act
        exec_task.run()

        # Assert — update_benchmark_run called with FAILED status
        update_run_calls = exec_task._data_api.update_benchmark_run.call_args_list  # type: ignore[attr-defined]
        persisted_statuses = [c.args[0].status for c in update_run_calls if c.args]
        assert BenchmarkRunStatus.FAILED in persisted_statuses

    def test_total_tasks_persisted_after_initialize(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        result = _make_result(status=BenchmarkResultStatus.NOT_COMPLETED)
        task = _make_task()
        provider = mocker.Mock(spec=LLMProviderApi)

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = [result]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.return_value = [result]  # type: ignore[attr-defined]
        exec_task._provider_registry.get_provider.return_value = provider  # type: ignore[attr-defined]
        provider.inference_sync.return_value = _make_inference_response()
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]

        # Act
        exec_task.run()

        # Assert — at least one update_benchmark_run call has total_tasks > 0
        update_run_calls = exec_task._data_api.update_benchmark_run.call_args_list  # type: ignore[attr-defined]
        persisted_totals = [c.args[0].total_tasks for c in update_run_calls if c.args and c.args[0].total_tasks]
        assert any(t > 0 for t in persisted_totals)

    def test_completed_tasks_debounced(self, mocker: MockerFixture) -> None:
        # Arrange — 20 tasks; debounce threshold is every 5 completions
        exec_task = _make_exec_task(mocker)
        run = _make_run(run_mode=RunMode.SPEED)
        results = [_make_result(task_id=f"t{i}", status=BenchmarkResultStatus.NOT_COMPLETED) for i in range(20)]
        tasks = [_make_task(f"t{i}") for i in range(20)]
        provider = mocker.Mock(spec=LLMProviderApi)

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = tasks  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = results  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run_with_status.return_value = results  # type: ignore[attr-defined]
        exec_task._provider_registry.get_provider.return_value = provider  # type: ignore[attr-defined]
        provider.inference_sync.return_value = _make_inference_response()
        exec_task._judge_prompt_service.build_inference_prompt.return_value = ("q?", "")  # type: ignore[attr-defined]
        exec_task._task_loader.get_task.side_effect = lambda tid: next(t for t in tasks if t.task_id == tid)  # type: ignore[attr-defined]

        # Act
        exec_task.run()

        # Assert — total update_benchmark_run calls < 20 (debounce prevents per-task writes)
        update_count = exec_task._data_api.update_benchmark_run.call_count  # type: ignore[attr-defined]
        assert update_count < 20

    def test_stopped_run_does_not_persist_completed_or_failed_status(self, mocker: MockerFixture) -> None:
        # Arrange
        exec_task = _make_exec_task(mocker)
        run = _make_run()
        task = _make_task()

        exec_task._data_api.retrieve_benchmark_run.return_value = run  # type: ignore[attr-defined]
        exec_task._task_loader.load_tasks.return_value = [task]  # type: ignore[attr-defined]
        exec_task._data_api.retrieve_benchmark_results_for_run.return_value = []  # type: ignore[attr-defined]

        # Act — stop before run so pipeline sees stop after initializing
        exec_task.stop()
        exec_task.run()

        # Assert — no COMPLETED or FAILED status persisted (run stays NOT_COMPLETED)
        update_run_calls = exec_task._data_api.update_benchmark_run.call_args_list  # type: ignore[attr-defined]
        persisted_statuses = [c.args[0].status for c in update_run_calls if c.args]
        assert BenchmarkRunStatus.COMPLETED not in persisted_statuses
        assert BenchmarkRunStatus.FAILED not in persisted_statuses
