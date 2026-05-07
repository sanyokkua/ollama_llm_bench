"""Unit tests for Phase 2 event dataclasses and new StrEnums in models.py."""

from dataclasses import FrozenInstanceError

import pytest

from ollama_llm_bench.backend.core.models import (
    AppSettingsChangedEvent,
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResultStatus,
    BenchmarkResumedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    LogEntryType,
    ModelDescriptor,
    ModelSwitchEvent,
    ModeSwitchEvent,
    PauseReason,
    PipelineStage,
    ProgressUpdateEvent,
    ProviderHealthCheckEvent,
    ProviderSwitchEvent,
    RunMode,
    StopReason,
    StreamingChunkEvent,
    TaskCompletedEvent,
    TaskSwitchEvent,
    TaskType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DESCRIPTOR = ModelDescriptor(
    provider_id="ollama_local",
    provider_type="openai_compatible",
    model_name="llama3.1:8b",
    display_label="ollama_local / llama3.1:8b",
)


# ---------------------------------------------------------------------------
# TestNewEnums
# ---------------------------------------------------------------------------


class TestNewEnums:
    def test_pipeline_stage_values(self) -> None:
        assert PipelineStage.INITIALIZING.value == "Initializing"
        assert PipelineStage.BENCHMARKING.value == "Benchmarking"
        assert PipelineStage.JUDGING.value == "Judging"
        assert PipelineStage.FINISHED.value == "Finished"
        assert PipelineStage.FAILED.value == "Failed"
        assert len(PipelineStage) == 5

    def test_eval_layer_values(self) -> None:
        assert EvalLayer.RULE_BASED.value == "rule_based"
        assert EvalLayer.KEYWORD.value == "keyword"
        assert EvalLayer.COSINE.value == "cosine"
        assert EvalLayer.LLM_JUDGE.value == "llm_judge"
        assert len(EvalLayer) == 4

    def test_eval_verdict_values(self) -> None:
        assert EvalVerdict.PASS.value == "pass"
        assert EvalVerdict.FAIL.value == "fail"
        assert EvalVerdict.UNKNOWN.value == "unknown"
        assert len(EvalVerdict) == 3

    def test_pause_reason_values(self) -> None:
        assert PauseReason.USER.value == "user"
        assert PauseReason.EVENT_POLICY.value == "event_policy"
        assert PauseReason.PROVIDER_ERROR.value == "provider_error"
        assert len(PauseReason) == 3

    def test_stop_reason_values(self) -> None:
        assert StopReason.USER.value == "user"
        assert StopReason.FATAL_ERROR.value == "fatal_error"
        assert len(StopReason) == 2

    def test_log_entry_type_values(self) -> None:
        assert LogEntryType.TASK_START.value == "task_start"
        assert LogEntryType.PROMPT.value == "prompt"
        assert LogEntryType.STREAM_CHUNK.value == "stream_chunk"
        assert LogEntryType.THINKING_BLOCK.value == "thinking_block"
        assert LogEntryType.INFERENCE_COMPLETE.value == "inference_complete"
        assert LogEntryType.JUDGE_RESULT.value == "judge_result"
        assert LogEntryType.ERROR.value == "error"
        assert LogEntryType.SYSTEM.value == "system"
        assert len(LogEntryType) == 8


# ---------------------------------------------------------------------------
# TestEvaluationResult
# ---------------------------------------------------------------------------


class TestEvaluationResult:
    def test_evaluation_result_fields(self) -> None:
        result = EvaluationResult(
            verdict=EvalVerdict.PASS,
            score=0.9,
            reasoning="All checks passed",
            is_terminal=True,
            layer=EvalLayer.RULE_BASED,
        )

        assert result.verdict == EvalVerdict.PASS
        assert result.score == 0.9
        assert result.reasoning == "All checks passed"
        assert result.is_terminal is True
        assert result.layer == EvalLayer.RULE_BASED

    def test_evaluation_result_score_round_trip(self) -> None:
        result = EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning="Borderline",
            is_terminal=False,
            layer=EvalLayer.COSINE,
        )

        assert result.score == 0.5

    def test_evaluation_result_is_frozen(self) -> None:
        result = EvaluationResult(
            verdict=EvalVerdict.FAIL,
            score=0.0,
            reasoning="Failed",
            is_terminal=True,
            layer=EvalLayer.KEYWORD,
        )

        with pytest.raises(FrozenInstanceError):
            result.score = 1.0  # type: ignore[misc]

    def test_evaluation_result_new_metadata_defaults(self) -> None:
        result = EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning="test",
            is_terminal=False,
            layer=EvalLayer.RULE_BASED,
        )

        assert result.missing_exact_terms == ()
        assert result.found_forbidden_terms == ()
        assert result.semantic_term_scores == ()
        assert result.judge_time_ms is None
        assert result.judge_completion_tokens is None
        assert result.judge_prompt_template is None


# ---------------------------------------------------------------------------
# TestLifecycleEvents
# ---------------------------------------------------------------------------


class TestLifecycleEvents:
    def test_benchmark_started_event_models_is_tuple(self) -> None:
        event = BenchmarkStartedEvent(
            run_id=1,
            total_tasks=10,
            models=(_DESCRIPTOR,),
            run_mode=RunMode.FULL_GRADING,
        )

        assert isinstance(event.models, tuple)
        assert event.models[0] is _DESCRIPTOR
        assert event.total_tasks == 10
        assert event.run_mode == RunMode.FULL_GRADING

    def test_benchmark_started_event_is_frozen(self) -> None:
        event = BenchmarkStartedEvent(
            run_id=1,
            total_tasks=5,
            models=(),
            run_mode=RunMode.SPEED,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_benchmark_paused_event_fields(self) -> None:
        event = BenchmarkPausedEvent(
            run_id=2,
            pause_reason=PauseReason.USER,
            paused_at_stage=PipelineStage.BENCHMARKING,
        )

        assert event.run_id == 2
        assert event.pause_reason == PauseReason.USER
        assert event.paused_at_stage == PipelineStage.BENCHMARKING

    def test_benchmark_paused_event_is_frozen(self) -> None:
        event = BenchmarkPausedEvent(
            run_id=2,
            pause_reason=PauseReason.PROVIDER_ERROR,
            paused_at_stage=PipelineStage.JUDGING,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_benchmark_resumed_event_is_frozen(self) -> None:
        event = BenchmarkResumedEvent(run_id=3)

        assert event.run_id == 3
        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_benchmark_stopped_event_is_frozen(self) -> None:
        event = BenchmarkStoppedEvent(run_id=4, stop_reason=StopReason.USER)

        assert event.stop_reason == StopReason.USER
        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_benchmark_finished_event_fields(self) -> None:
        event = BenchmarkFinishedEvent(
            run_id=5,
            total_time_ms=12345.6,
            completed_count=10,
            failed_count=0,
        )

        assert event.total_time_ms == 12345.6
        assert event.completed_count == 10
        assert event.failed_count == 0

    def test_benchmark_finished_event_is_frozen(self) -> None:
        event = BenchmarkFinishedEvent(
            run_id=5,
            total_time_ms=1000.0,
            completed_count=5,
            failed_count=1,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestSwitchEvents
# ---------------------------------------------------------------------------


class TestSwitchEvents:
    def test_provider_switch_event_nullable_from_provider(self) -> None:
        event = ProviderSwitchEvent(
            run_id=1,
            from_provider_id=None,
            to_provider_id="ollama_local",
            provider_label="Ollama Local",
        )

        assert event.from_provider_id is None
        assert event.to_provider_id == "ollama_local"

    def test_provider_switch_event_is_frozen(self) -> None:
        event = ProviderSwitchEvent(
            run_id=1,
            from_provider_id="a",
            to_provider_id="b",
            provider_label="B",
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_provider_health_check_event_is_frozen(self) -> None:
        event = ProviderHealthCheckEvent(
            run_id=1,
            provider_id="ollama_local",
            is_healthy=True,
            error_message=None,
        )

        assert event.is_healthy is True
        assert event.error_message is None
        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_model_switch_event_nullable_from_model(self) -> None:
        event = ModelSwitchEvent(
            run_id=1,
            from_model=None,
            to_model=_DESCRIPTOR,
        )

        assert event.from_model is None
        assert event.to_model is _DESCRIPTOR

    def test_model_switch_event_is_frozen(self) -> None:
        event = ModelSwitchEvent(
            run_id=1,
            from_model="old_model",
            to_model=_DESCRIPTOR,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_task_switch_event_fields(self) -> None:
        event = TaskSwitchEvent(
            run_id=1,
            model=_DESCRIPTOR,
            task_id="task_001",
            task_category="reasoning",
            task_type=TaskType.REASONING,
            task_number=3,
            tasks_total=20,
        )

        assert event.task_id == "task_001"
        assert event.task_type == TaskType.REASONING
        assert event.task_number == 3
        assert event.tasks_total == 20

    def test_task_switch_event_is_frozen(self) -> None:
        event = TaskSwitchEvent(
            run_id=1,
            model=_DESCRIPTOR,
            task_id="t",
            task_category="cat",
            task_type=TaskType.FACTUAL_QA,
            task_number=1,
            tasks_total=5,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_mode_switch_event_is_frozen(self) -> None:
        event = ModeSwitchEvent(
            run_id=1,
            from_stage=PipelineStage.BENCHMARKING,
            to_stage=PipelineStage.JUDGING,
        )

        assert event.from_stage == PipelineStage.BENCHMARKING
        assert event.to_stage == PipelineStage.JUDGING
        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestCompletionEvents
# ---------------------------------------------------------------------------


class TestCompletionEvents:
    def test_task_completed_event_nullable_fields(self) -> None:
        event = TaskCompletedEvent(
            run_id=1,
            result_id=42,
            model=_DESCRIPTOR,
            task_id="task_001",
            status=BenchmarkResultStatus.COMPLETED,
            total_time_ms=None,
            ttft_ms=None,
            final_verdict=None,
        )

        assert event.total_time_ms is None
        assert event.ttft_ms is None
        assert event.final_verdict is None
        assert event.status == BenchmarkResultStatus.COMPLETED

    def test_task_completed_event_is_frozen(self) -> None:
        event = TaskCompletedEvent(
            run_id=1,
            result_id=1,
            model=_DESCRIPTOR,
            task_id="t",
            status=BenchmarkResultStatus.FAILED,
            total_time_ms=500.0,
            ttft_ms=50.0,
            final_verdict="fail",
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_judge_started_event_is_frozen(self) -> None:
        event = JudgeStartedEvent(
            run_id=1,
            result_id=7,
            layer=EvalLayer.LLM_JUDGE,
        )

        assert event.layer == EvalLayer.LLM_JUDGE
        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_judge_completed_event_resolved_flag(self) -> None:
        event = JudgeCompletedEvent(
            run_id=1,
            result_id=7,
            layer=EvalLayer.COSINE,
            verdict=EvalVerdict.PASS,
            resolved=True,
        )

        assert event.verdict == EvalVerdict.PASS
        assert event.resolved is True

    def test_judge_completed_event_is_frozen(self) -> None:
        event = JudgeCompletedEvent(
            run_id=1,
            result_id=7,
            layer=EvalLayer.KEYWORD,
            verdict=EvalVerdict.UNKNOWN,
            resolved=False,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestStreamingAndProgressEvents
# ---------------------------------------------------------------------------


class TestStreamingAndProgressEvents:
    def test_streaming_chunk_event_thinking_block_flag(self) -> None:
        event = StreamingChunkEvent(
            run_id=1,
            result_id=5,
            model_name="llama3.1:8b",
            task_id="task_001",
            chunk_text="Hello",
            is_thinking_block=True,
        )

        assert event.chunk_text == "Hello"
        assert event.is_thinking_block is True

    def test_streaming_chunk_event_is_frozen(self) -> None:
        event = StreamingChunkEvent(
            run_id=1,
            result_id=5,
            model_name="m",
            task_id="t",
            chunk_text="tok",
            is_thinking_block=False,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]

    def test_progress_update_event_nullable_estimated_remaining(self) -> None:
        event = ProgressUpdateEvent(
            run_id=1,
            stage=PipelineStage.BENCHMARKING,
            current_provider="ollama_local",
            current_model="llama3.1:8b",
            current_task="task_005",
            tasks_completed=5,
            tasks_total=20,
            start_time_ms=1000.0,
            current_time_ms=5000.0,
            estimated_remaining_ms=None,
        )

        assert event.tasks_completed == 5
        assert event.tasks_total == 20
        assert event.estimated_remaining_ms is None

    def test_progress_update_event_with_eta(self) -> None:
        event = ProgressUpdateEvent(
            run_id=1,
            stage=PipelineStage.JUDGING,
            current_provider="ollama_local",
            current_model="llama3.1:8b",
            current_task="task_010",
            tasks_completed=10,
            tasks_total=20,
            start_time_ms=1000.0,
            current_time_ms=6000.0,
            estimated_remaining_ms=5000.0,
        )

        assert event.estimated_remaining_ms == 5000.0
        assert event.stage == PipelineStage.JUDGING

    def test_progress_update_event_is_frozen(self) -> None:
        event = ProgressUpdateEvent(
            run_id=1,
            stage=PipelineStage.INITIALIZING,
            current_provider="p",
            current_model="m",
            current_task="t",
            tasks_completed=0,
            tasks_total=10,
            start_time_ms=0.0,
            current_time_ms=100.0,
            estimated_remaining_ms=900.0,
        )

        with pytest.raises(FrozenInstanceError):
            event.run_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestAppSettingsChangedEvent
# ---------------------------------------------------------------------------


class TestAppSettingsChangedEvent:
    def test_stores_changed_keys_as_tuple(self) -> None:
        evt = AppSettingsChangedEvent(changed_keys=("ui.theme", "ui.score_display_format"))
        assert evt.changed_keys == ("ui.theme", "ui.score_display_format")

    def test_empty_changed_keys(self) -> None:
        evt = AppSettingsChangedEvent(changed_keys=())
        assert evt.changed_keys == ()

    def test_is_frozen(self) -> None:
        evt = AppSettingsChangedEvent(changed_keys=("ui.theme",))
        with pytest.raises((AttributeError, FrozenInstanceError)):
            evt.changed_keys = ()  # type: ignore[misc]

    def test_single_key(self) -> None:
        evt = AppSettingsChangedEvent(changed_keys=("feature.streaming_enabled",))
        assert len(evt.changed_keys) == 1
        assert evt.changed_keys[0] == "feature.streaming_enabled"
