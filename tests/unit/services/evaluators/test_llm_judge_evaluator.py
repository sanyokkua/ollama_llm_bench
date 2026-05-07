"""Unit tests for LLMJudgeEvaluator (Layer 4) and parse_v2_judge_response()."""

import logging

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    JudgePromptServiceApi,
    LLMJudgeEvaluatorApi,
    LLMProviderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvalVerdict,
    InferenceResponse,
    TaskType,
)
from ollama_llm_bench.backend.services.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
from ollama_llm_bench.backend.utils.text_utils import parse_v2_judge_response

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_task(
    *,
    task_type: TaskType = TaskType.FACTUAL_QA,
    question: str = "What is the capital of France?",
    golden_answer: str = "Paris",
    pass_criteria: str = "Mentions Paris",  # noqa: S107
    fail_criteria: str = "Does not mention Paris",
) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        category="geography",
        sub_category="capitals",
        task_type=task_type,
        question=question,
        golden_answer=golden_answer,
        pass_criteria=pass_criteria,
        fail_criteria=fail_criteria,
        difficulty=Difficulty.EASY,
    )


def _make_result(
    *,
    sanitized_response: str | None = "Paris is the capital.",
    raw_response: str | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        sanitized_response=sanitized_response,
        raw_response=raw_response,
    )


def _make_inference_response(
    content: str = "",
    *,
    has_error: bool = False,
    error_message: str | None = None,
    total_time_ms: int = 0,
    completion_tokens: int = 0,
) -> InferenceResponse:
    return InferenceResponse(
        llm_response=content,
        has_error=has_error,
        error_message=error_message,
        total_time_ms=total_time_ms,
        completion_tokens=completion_tokens,
    )


def _make_evaluator(
    mocker: MockerFixture,
) -> tuple[
    LLMJudgeEvaluator,
    "MockerFixture.Mock",
    "MockerFixture.Mock",
    "MockerFixture.Mock",
]:
    """Return (evaluator, mock_registry, mock_prompt_svc, mock_provider)."""
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_prompt_svc = mocker.Mock(spec=JudgePromptServiceApi)
    mock_provider = mocker.Mock(spec=LLMProviderApi)

    mock_registry.get_provider.return_value = mock_provider
    mock_prompt_svc.build_judge_prompt.return_value = ("user_prompt", "system_prompt")
    mock_provider.supports_structured_output.return_value = False

    evaluator = LLMJudgeEvaluator(
        provider_registry=mock_registry,
        judge_prompt_service=mock_prompt_svc,
    )
    return evaluator, mock_registry, mock_prompt_svc, mock_provider


# ---------------------------------------------------------------------------
# parse_v2_judge_response
# ---------------------------------------------------------------------------


class TestParseV2JudgeResponseValidJson:
    def test_pass_verdict_returns_false_and_pass(self) -> None:
        text = '{"verdict": "pass", "score": 0.9, "reasoning": "correct answer"}'
        has_error, verdict, score, reasoning = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.PASS
        assert score == pytest.approx(0.9)
        assert reasoning == "correct answer"

    def test_fail_verdict_returns_false_and_fail(self) -> None:
        text = '{"verdict": "fail", "score": 0.1, "reasoning": "wrong answer"}'
        has_error, verdict, score, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.FAIL
        assert score == pytest.approx(0.1)

    def test_unknown_verdict_string_returns_unknown(self) -> None:
        text = '{"verdict": "maybe", "score": 0.5, "reasoning": "unclear"}'
        has_error, verdict, _, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.UNKNOWN

    def test_verdict_case_insensitive_pass(self) -> None:
        text = '{"verdict": "PASS", "score": 0.8, "reasoning": "ok"}'
        _, verdict, _, _ = parse_v2_judge_response(text)
        assert verdict is EvalVerdict.PASS

    def test_verdict_case_insensitive_fail(self) -> None:
        text = '{"verdict": "FAIL", "score": 0.2, "reasoning": "nope"}'
        _, verdict, _, _ = parse_v2_judge_response(text)
        assert verdict is EvalVerdict.FAIL

    def test_score_clamped_above_one(self) -> None:
        text = '{"verdict": "pass", "score": 1.5, "reasoning": "high"}'
        _, _, score, _ = parse_v2_judge_response(text)
        assert score == pytest.approx(1.0)

    def test_score_clamped_below_zero(self) -> None:
        text = '{"verdict": "fail", "score": -0.5, "reasoning": "negative"}'
        _, _, score, _ = parse_v2_judge_response(text)
        assert score == pytest.approx(0.0)

    def test_missing_reasoning_field_returns_empty_string(self) -> None:
        text = '{"verdict": "pass", "score": 0.7}'
        has_error, _, _, reasoning = parse_v2_judge_response(text)
        assert has_error is False
        assert reasoning == ""

    def test_missing_score_field_defaults_to_zero(self) -> None:
        text = '{"verdict": "pass", "reasoning": "ok"}'
        has_error, _, score, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert score == pytest.approx(0.0)

    def test_whitespace_around_json_is_stripped(self) -> None:
        text = '  \n{"verdict": "pass", "score": 0.9, "reasoning": "fine"}\n  '
        has_error, verdict, _, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.PASS


class TestParseV2JudgeResponseRegexFallback:
    def test_malformed_json_with_verdict_and_score_succeeds(self) -> None:
        text = 'Here is the result: "verdict": "pass", "score": 0.85, extra garbage'
        has_error, verdict, score, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.PASS
        assert score == pytest.approx(0.85)

    def test_regex_fallback_fail_verdict(self) -> None:
        text = 'bad json { "verdict": "fail", "score": 0.2 } and more'
        has_error, verdict, _, _ = parse_v2_judge_response(text)
        assert has_error is False
        assert verdict is EvalVerdict.FAIL

    def test_regex_fallback_with_reasoning_extracts_it(self) -> None:
        text = '"verdict": "pass", "score": 0.9, "reasoning": "well done"'
        has_error, _, _, reasoning = parse_v2_judge_response(text)
        assert has_error is False
        assert reasoning == "well done"

    def test_regex_fallback_without_reasoning_returns_empty(self) -> None:
        text = '"verdict": "pass", "score": 0.9'
        has_error, _, _, reasoning = parse_v2_judge_response(text)
        assert has_error is False
        assert reasoning == ""

    def test_regex_fallback_score_clamped(self) -> None:
        text = '"verdict": "fail", "score": 2.0'
        _, _, score, _ = parse_v2_judge_response(text)
        assert score == pytest.approx(1.0)

    def test_regex_fallback_verdict_case_insensitive(self) -> None:
        text = '"verdict": "PASS", "score": 0.7'
        _, verdict, _, _ = parse_v2_judge_response(text)
        assert verdict is EvalVerdict.PASS


class TestParseV2JudgeResponseTotalFailure:
    def test_empty_string_returns_error(self) -> None:
        has_error, verdict, score, _ = parse_v2_judge_response("")
        assert has_error is True
        assert verdict is EvalVerdict.UNKNOWN
        assert score == pytest.approx(0.0)

    def test_random_text_returns_error(self) -> None:
        has_error, verdict, score, _ = parse_v2_judge_response("no json here at all")
        assert has_error is True
        assert verdict is EvalVerdict.UNKNOWN
        assert score == pytest.approx(0.0)

    def test_json_missing_verdict_field_falls_back_to_error(self) -> None:
        # JSON parses but no "verdict"; regex also fails to find pass/fail
        has_error, verdict, _, _ = parse_v2_judge_response('{"score": 0.5, "reasoning": "ok"}')
        # JSON path succeeds, returning UNKNOWN verdict (not an error)
        assert has_error is False
        assert verdict is EvalVerdict.UNKNOWN

    def test_error_message_contains_preview(self) -> None:
        text = "totally unparseable garbage"
        has_error, _, _, reasoning = parse_v2_judge_response(text)
        assert has_error is True
        assert "Could not parse" in reasoning

    def test_warning_logged_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="ollama_llm_bench.backend.utils.text_utils"):
            parse_v2_judge_response("no json here at all")
        assert any("parse_v2_judge_response_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — layer property
# ---------------------------------------------------------------------------


class TestLayerProperty:
    def test_layer_returns_llm_judge(self, mocker: MockerFixture) -> None:
        evaluator, _, _, _ = _make_evaluator(mocker)
        assert evaluator.layer is EvalLayer.LLM_JUDGE


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — interface conformance
# ---------------------------------------------------------------------------


class TestInterfaceConformance:
    def test_isinstance_llm_judge_evaluator_api(self, mocker: MockerFixture) -> None:
        evaluator, _, _, _ = _make_evaluator(mocker)
        assert isinstance(evaluator, LLMJudgeEvaluatorApi)


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — successful evaluation
# ---------------------------------------------------------------------------


class TestEvaluateSuccess:
    def test_pass_verdict_returns_terminal_pass(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":0.9,"reasoning":"correct"}',
            total_time_ms=1500,
            completion_tokens=42,
        )
        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.PASS
        assert result.is_terminal is True
        assert result.score == pytest.approx(0.9)
        assert result.reasoning == "correct"
        assert result.layer is EvalLayer.LLM_JUDGE
        assert result.judge_time_ms is not None
        assert result.judge_completion_tokens is not None
        assert result.judge_prompt_template is not None

    def test_fail_verdict_returns_terminal_fail(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"fail","score":0.2,"reasoning":"wrong answer"}'
        )
        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.FAIL
        assert result.is_terminal is True

    def test_prompts_built_and_passed_correctly(self, mocker: MockerFixture) -> None:
        evaluator, _, mock_prompt_svc, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":1.0,"reasoning":"ok"}'
        )
        task = _make_task()
        result_obj = _make_result()
        evaluator.evaluate(task, result_obj, judge_provider_id="ollama", judge_model="llama3")

        mock_prompt_svc.build_judge_prompt.assert_called_once_with(task, result_obj)

    def test_inference_called_with_correct_args(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":0.8,"reasoning":"fine"}'
        )
        evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        call_kwargs = mock_provider.inference_sync.call_args.kwargs
        assert call_kwargs["model"] == "llama3"
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["max_tokens"] == 256
        assert isinstance(call_kwargs["messages"], list)
        assert len(call_kwargs["messages"]) == 2

    def test_messages_contain_system_and_user_roles(self, mocker: MockerFixture) -> None:
        evaluator, _, mock_prompt_svc, mock_provider = _make_evaluator(mocker)
        mock_prompt_svc.build_judge_prompt.return_value = ("the question", "be a judge")
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":0.9,"reasoning":"ok"}'
        )
        evaluator.evaluate(_make_task(), _make_result(), judge_provider_id="ollama", judge_model="m")
        messages = mock_provider.inference_sync.call_args.kwargs["messages"]
        roles = {m["role"] for m in messages}
        assert "system" in roles
        assert "user" in roles


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — provider error
# ---------------------------------------------------------------------------


class TestProviderError:
    def test_get_provider_raises_returns_non_terminal_unknown(self, mocker: MockerFixture) -> None:
        evaluator, mock_registry, _, _ = _make_evaluator(mocker)
        mock_registry.get_provider.side_effect = KeyError("not found")

        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="missing",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.UNKNOWN
        assert result.is_terminal is False
        assert result.layer is EvalLayer.LLM_JUDGE

    def test_get_provider_raises_logs_warning(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        evaluator, mock_registry, _, _ = _make_evaluator(mocker)
        mock_registry.get_provider.side_effect = ValueError("bad provider")

        with caplog.at_level(
            logging.WARNING,
            logger="ollama_llm_bench.backend.services.evaluators.llm_judge_evaluator",
        ):
            evaluator.evaluate(
                _make_task(),
                _make_result(),
                judge_provider_id="bad",
                judge_model="llama3",
            )
        assert any("llm_judge_provider_not_found" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — inference error
# ---------------------------------------------------------------------------


class TestInferenceError:
    def test_inference_sync_raises_returns_non_terminal_unknown(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.side_effect = RuntimeError("timeout")

        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.UNKNOWN
        assert result.is_terminal is False

    def test_inference_sync_raises_logs_warning(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.side_effect = RuntimeError("timeout")

        with caplog.at_level(
            logging.WARNING,
            logger="ollama_llm_bench.backend.services.evaluators.llm_judge_evaluator",
        ):
            evaluator.evaluate(
                _make_task(),
                _make_result(),
                judge_provider_id="ollama",
                judge_model="llama3",
            )
        assert any("llm_judge_inference_failed" in r.message for r in caplog.records)

    def test_inference_response_has_error_returns_non_terminal_unknown(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            "", has_error=True, error_message="model not loaded"
        )
        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.UNKNOWN
        assert result.is_terminal is False


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — parse error
# ---------------------------------------------------------------------------


class TestParseError:
    def test_unparseable_response_returns_non_terminal_unknown(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response("sorry I cannot help with that")
        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        assert result.verdict is EvalVerdict.UNKNOWN
        assert result.is_terminal is False

    def test_parse_error_logs_warning(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response("not json")

        with caplog.at_level(
            logging.WARNING,
            logger="ollama_llm_bench.backend.services.evaluators.llm_judge_evaluator",
        ):
            evaluator.evaluate(
                _make_task(),
                _make_result(),
                judge_provider_id="ollama",
                judge_model="llama3",
            )
        assert any("llm_judge_parse_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator — structured output capability check
# ---------------------------------------------------------------------------


class TestStructuredOutputFlag:
    def test_supports_structured_output_is_called(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":1.0,"reasoning":"ok"}'
        )
        evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        mock_provider.supports_structured_output.assert_called_once()

    def test_supports_structured_output_true_still_calls_inference(self, mocker: MockerFixture) -> None:
        evaluator, _, _, mock_provider = _make_evaluator(mocker)
        mock_provider.supports_structured_output.return_value = True
        mock_provider.inference_sync.return_value = _make_inference_response(
            '{"verdict":"pass","score":0.9,"reasoning":"ok"}'
        )
        result = evaluator.evaluate(
            _make_task(),
            _make_result(),
            judge_provider_id="ollama",
            judge_model="llama3",
        )
        mock_provider.inference_sync.assert_called_once()
        assert result.verdict is EvalVerdict.PASS
