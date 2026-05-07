"""Unit tests for RuleBasedEvaluator — Layer 1 deterministic response checks."""

import pytest

from ollama_llm_bench.backend.core.interfaces import EvaluatorApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvalVerdict,
    ResponseScope,
    TaskType,
)
from ollama_llm_bench.backend.services.evaluators.rule_based_evaluator import (
    _ERROR_MARKERS,
    _MIN_RESPONSE_CHARS,
    RuleBasedEvaluator,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_task(question: str = "What is 2+2?") -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        category="math",
        sub_category="arithmetic",
        task_type=TaskType.FACTUAL_QA,
        question=question,
        golden_answer="4",
        pass_criteria="",
        fail_criteria="",
        difficulty=Difficulty.EASY,
        response_scope=ResponseScope.CONTAINS,
    )


def _make_result(
    *,
    sanitized_response: str | None = None,
    raw_response: str | None = None,
    has_inference_error: bool = False,
    inference_error_message: str | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        sanitized_response=sanitized_response,
        raw_response=raw_response,
        has_inference_error=has_inference_error,
        inference_error_message=inference_error_message,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLayerProperty:
    def test_layer_returns_rule_based(self) -> None:
        evaluator = RuleBasedEvaluator()
        assert evaluator.layer is EvalLayer.RULE_BASED


class TestInterfaceConformance:
    def test_isinstance_check_passes(self) -> None:
        evaluator = RuleBasedEvaluator()
        assert isinstance(evaluator, EvaluatorApi)


class TestInferenceErrorCheck:
    def test_inference_error_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(
            sanitized_response="some response",
            has_inference_error=True,
            inference_error_message="connection refused",
        )

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert outcome.score == 0.0
        assert outcome.layer is EvalLayer.RULE_BASED
        assert "connection refused" in outcome.reasoning

    def test_inference_error_without_message_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(has_inference_error=True)

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True


class TestEmptyCheck:
    def test_empty_string_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert "empty" in outcome.reasoning.lower()

    def test_whitespace_only_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="   \n\t  ")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_none_sanitized_and_none_raw_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response=None, raw_response=None)

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_none_sanitized_falls_back_to_raw_response(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        # raw_response is a valid non-empty response well above min length
        result = _make_result(sanitized_response=None, raw_response="The answer is four.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestEchoCheck:
    def test_response_starting_with_question_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        question = "What is 2+2?"
        task = _make_task(question=question)
        result = _make_result(sanitized_response="What is 2+2? The answer is 4.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert "echo" in outcome.reasoning.lower()

    def test_response_starting_with_question_case_insensitive(self) -> None:
        evaluator = RuleBasedEvaluator()
        question = "WHAT IS 2+2?"
        task = _make_task(question=question)
        result = _make_result(sanitized_response="what is 2+2? The answer is 4.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_echo_check_uses_first_100_chars_of_question(self) -> None:
        evaluator = RuleBasedEvaluator()
        # Question longer than 100 chars; response starts with first 100 chars
        long_question = "A" * 120
        task = _make_task(question=long_question)
        prefix = long_question[:100].lower()
        result = _make_result(sanitized_response=prefix + " some extra content here that is long enough")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_response_not_starting_with_question_passes_echo_check(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task(question="What is 2+2?")
        result = _make_result(sanitized_response="The answer is definitely four.")

        outcome = evaluator.evaluate(task, result)

        # Should not fail on echo check; may still pass other checks
        assert outcome.verdict is not EvalVerdict.FAIL or "echo" not in outcome.reasoning.lower()


class TestTooShortCheck:
    def test_response_under_min_chars_returns_terminal_fail(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        short_response = "x" * (_MIN_RESPONSE_CHARS - 1)
        result = _make_result(sanitized_response=short_response)

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert "too short" in outcome.reasoning.lower()

    def test_response_exactly_min_chars_passes_too_short_check(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        # Exactly _MIN_RESPONSE_CHARS chars, no echo, no error markers
        exact_response = "z" * _MIN_RESPONSE_CHARS
        result = _make_result(sanitized_response=exact_response)

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_response_one_char_too_short_fails(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="a" * (_MIN_RESPONSE_CHARS - 1))

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert str(_MIN_RESPONSE_CHARS - 1) in outcome.reasoning


class TestErrorMarkerCheck:
    @pytest.mark.parametrize(
        "marker",
        sorted(_ERROR_MARKERS),
        ids=[m.replace(" ", "_").replace("(", "").replace(")", "") for m in sorted(_ERROR_MARKERS)],
    )
    def test_error_marker_in_response_returns_terminal_fail(self, marker: str) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        long_enough = "x" * 50
        result = _make_result(sanitized_response=f"{long_enough} {marker} some text")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert "error marker" in outcome.reasoning.lower()

    def test_error_marker_check_is_case_insensitive(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="x" * 30 + " ERROR: something went wrong")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_no_error_marker_passes_check(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="The answer is four, which equals 2+2.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestAllPass:
    def test_valid_response_returns_unknown_non_terminal(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task(question="What is the capital of France?")
        result = _make_result(sanitized_response="The capital of France is Paris.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False
        assert outcome.score == 0.5
        assert outcome.layer is EvalLayer.RULE_BASED
        assert "all rule-based checks passed" in outcome.reasoning.lower()

    def test_all_pass_reasoning_is_descriptive(self) -> None:
        evaluator = RuleBasedEvaluator()
        task = _make_task()
        result = _make_result(sanitized_response="The answer to this question is four (4).")

        outcome = evaluator.evaluate(task, result)

        assert outcome.reasoning != ""
