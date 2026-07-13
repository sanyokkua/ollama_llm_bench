"""Tests for backend/evaluation/_internal/judge/parsing.py (§8 of
08-P_judge_protocol.md). Task 9 appends the retry/exhaustion tests to this file."""

import pytest

from ollama_llm_bench.backend.domain import Verdict
from ollama_llm_bench.backend.evaluation._internal.judge.parsing import parse_judge_response


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
