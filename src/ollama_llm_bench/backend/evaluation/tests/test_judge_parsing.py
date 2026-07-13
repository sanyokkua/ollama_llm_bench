"""Tests for backend/evaluation/_internal/judge/parsing.py (§8 of
08-P_judge_protocol.md). Task 9 appends the retry/exhaustion tests to this file."""

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.domain import ChatResponse, Verdict
from ollama_llm_bench.backend.errors import HttpTimeoutError, ProviderContextLengthError
from ollama_llm_bench.backend.evaluation._internal.judge.evaluator import _JudgeEvaluatorImpl
from ollama_llm_bench.backend.evaluation._internal.judge.parsing import parse_judge_response
from ollama_llm_bench.backend.evaluation._internal.parameters import parse_evaluation_parameters
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome
from ollama_llm_bench.backend.evaluation.tests.conftest import (
    FakeLLMClient,
    make_cancellation_token,
    make_snapshot,
    make_task,
)
from ollama_llm_bench.backend.provider_registry import LLMClient

_TWO_CALLS = 2
_THREE_CALLS = 3
_RESOLVED_TOTAL_TIME_MS = 220


def test_clean_json_parses_strict_with_pass() -> None:
    """Proves: STORY-028-AC-5

    A clean {"verdict":"PASS","reasoning":"…"} body parses on the strict step.
    """
    parsed = parse_judge_response('{"verdict": "PASS", "reasoning": "It is correct."}')

    assert parsed is not None
    assert parsed.verdict == Verdict.PASS
    assert parsed.reasoning == "It is correct."


def test_lower_case_verdict_is_normalised() -> None:
    """Proves: STORY-028-AC-5

    A lower-case "pass" verdict is normalised to Verdict.PASS.
    """
    parsed = parse_judge_response('{"verdict": "pass", "reasoning": "ok"}')

    assert parsed is not None
    assert parsed.verdict == Verdict.PASS


def test_missing_reasoning_defaults_to_the_documented_placeholder() -> None:
    """Proves: STORY-028-AC-5

    A valid verdict with no reasoning field is accepted with the default
    reasoning string.
    """
    parsed = parse_judge_response('{"verdict": "FAIL"}')

    assert parsed is not None
    assert parsed.verdict == Verdict.FAIL
    assert parsed.reasoning == "(no reasoning provided by judge)"


def test_fenced_json_with_surrounding_prose_parses_leniently() -> None:
    """Proves: STORY-028-AC-5

    An object wrapped in ```json fences with surrounding prose parses on
    the lenient step.
    """
    body = 'Here is my evaluation:\n```json\n{"verdict": "FAIL", "reasoning": "Missing validation."}\n```'

    parsed = parse_judge_response(body)

    assert parsed is not None
    assert parsed.verdict == Verdict.FAIL
    assert parsed.reasoning == "Missing validation."


def test_key_adjacent_token_amid_prose_parses_leniently() -> None:
    """Proves: STORY-028-AC-5

    A PASS/FAIL token adjacent to the verdict key amid prose parses on the
    lenient step.
    """
    body = "My assessment is that verdict: FAIL because the response is incomplete."

    parsed = parse_judge_response(body)

    assert parsed is not None
    assert parsed.verdict == Verdict.FAIL


def test_prose_with_neither_token_is_malformed() -> None:
    """Proves: STORY-028-AC-5

    Prose containing neither PASS nor FAIL is malformed (returns None).
    """
    parsed = parse_judge_response("The candidate answer looks mostly right but I am not sure.")

    assert parsed is None


def test_extra_fields_are_ignored() -> None:
    """Proves: STORY-028-AC-5

    Extra fields (e.g. a numeric score) are accepted and ignored; no
    numeric value is stored anywhere on the parsed result.
    """
    parsed = parse_judge_response('{"verdict": "PASS", "reasoning": "ok", "score": 0.93}')

    assert parsed is not None
    assert parsed.verdict == Verdict.PASS
    assert not hasattr(parsed, "score")


@pytest.mark.parametrize(
    "body", ["PASS FAIL", "The result is PASS and also FAIL depending on interpretation."]
)
def test_both_tokens_with_no_key_association_is_malformed(body: str) -> None:
    """Proves: STORY-028-AC-5

    Both tokens present with no clear verdict-key association is malformed.
    """
    parsed = parse_judge_response(body)

    assert parsed is None


def test_malformed_response_recovers_on_stricter_retry() -> None:
    """Proves: STORY-028-AC-5

    A malformed first response, followed by a valid retry response,
    resolves the task in two calls with no ERRORED outcome.
    """
    client = FakeLLMClient(
        responses=[
            ChatResponse(text="not json at all", total_time_ms=100),
            ChatResponse(text='{"verdict": "PASS", "reasoning": "ok"}', total_time_ms=120),
        ]
    )
    parameters = parse_evaluation_parameters(make_snapshot({"eval.judge_max_parse_retries": "2"}))
    evaluator = _JudgeEvaluatorImpl(
        llm_client=client, model_name="judge-model", parameters=parameters
    )

    result = evaluator.evaluate(
        response="Paris.",
        system_prompt_sent=None,
        task=make_task(),
        timeout_ms=30_000,
        token=make_cancellation_token(),
    )

    assert result.outcome == JudgePhaseOutcome.RESOLVED
    assert result.verdict is not None
    assert result.verdict.value == "pass"
    assert len(client.requests) == _TWO_CALLS
    assert result.time_ms == _RESOLVED_TOTAL_TIME_MS


def test_exhausted_parse_retries_reports_errored_and_is_retryable() -> None:
    """Proves: STORY-028-AC-6

    Every one of judge_max_parse_retries + 1 attempts returning malformed
    responses reports PARSE_EXHAUSTED with judge_verdict=None and a
    diagnostic reasoning naming the attempt count.
    """
    client = FakeLLMClient(
        responses=[
            ChatResponse(text="nope", total_time_ms=100, completion_tokens=50),
            ChatResponse(text="still nope", total_time_ms=100, completion_tokens=50),
            ChatResponse(text="still nope again", total_time_ms=100, completion_tokens=50),
        ]
    )
    parameters = parse_evaluation_parameters(
        make_snapshot(
            {"eval.judge_max_parse_retries": "2", "eval.judge_max_completion_tokens": "4096"}
        )
    )
    evaluator = _JudgeEvaluatorImpl(
        llm_client=client, model_name="judge-model", parameters=parameters
    )

    result = evaluator.evaluate(
        response="Paris.",
        system_prompt_sent=None,
        task=make_task(),
        timeout_ms=30_000,
        token=make_cancellation_token(),
    )

    assert result.outcome == JudgePhaseOutcome.PARSE_EXHAUSTED
    assert result.verdict is None
    assert "3 attempts" in result.reasoning
    assert len(client.requests) == _THREE_CALLS


def test_exhausted_retries_truncated_at_cap_reports_budget_exhausted_diagnostic() -> None:
    """Proves: STORY-028-AC-6

    When the malformed responses were truncated at
    eval.judge_max_completion_tokens, the diagnostic is the budget-exhausted
    message rather than a bare parse-failure count.
    """
    client = FakeLLMClient(
        responses=[
            ChatResponse(
                text="reasoning that never finishes", total_time_ms=100, completion_tokens=64
            ),
            ChatResponse(text="still going", total_time_ms=100, completion_tokens=64),
        ]
    )
    parameters = parse_evaluation_parameters(
        make_snapshot(
            {"eval.judge_max_parse_retries": "1", "eval.judge_max_completion_tokens": "64"}
        )
    )
    evaluator = _JudgeEvaluatorImpl(
        llm_client=client, model_name="judge-model", parameters=parameters
    )

    result = evaluator.evaluate(
        response="Paris.",
        system_prompt_sent=None,
        task=make_task(),
        timeout_ms=30_000,
        token=make_cancellation_token(),
    )

    assert result.outcome == JudgePhaseOutcome.PARSE_EXHAUSTED
    assert "completion-token budget" in result.reasoning


def test_transport_failure_reports_transport_failure_not_errored(mocker: MockerFixture) -> None:
    """Proves: STORY-028-AC-5

    A judge transport failure (a non-context-length AppError) is reported
    as TRANSPORT_FAILURE with verdict=None, never PARSE_EXHAUSTED.
    """
    failing_client = mocker.Mock(spec=LLMClient)
    failing_client.chat.side_effect = HttpTimeoutError(message="timed out")
    parameters = parse_evaluation_parameters(make_snapshot())
    evaluator = _JudgeEvaluatorImpl(
        llm_client=failing_client, model_name="judge-model", parameters=parameters
    )

    result = evaluator.evaluate(
        response="Paris.",
        system_prompt_sent=None,
        task=make_task(),
        timeout_ms=30_000,
        token=make_cancellation_token(),
    )

    assert result.outcome == JudgePhaseOutcome.TRANSPORT_FAILURE
    assert result.verdict is None


def test_context_length_error_propagates_uncaught(mocker: MockerFixture) -> None:
    """Proves: STORY-028-AC-5

    A ProviderContextLengthError is never caught by the evaluator — it is a
    permanent, non-retried error surfaced uncaught to the caller (DD-46 §4.3).
    """
    overflowing_client = mocker.Mock(spec=LLMClient)
    overflowing_client.chat.side_effect = ProviderContextLengthError(message="prompt too long")
    parameters = parse_evaluation_parameters(make_snapshot())
    evaluator = _JudgeEvaluatorImpl(
        llm_client=overflowing_client, model_name="judge-model", parameters=parameters
    )

    with pytest.raises(ProviderContextLengthError):
        evaluator.evaluate(
            response="Paris.",
            system_prompt_sent=None,
            task=make_task(),
            timeout_ms=30_000,
            token=make_cancellation_token(),
        )
