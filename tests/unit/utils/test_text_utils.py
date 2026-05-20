"""Unit tests for parse_v2_judge_response robustness improvements."""

import pytest

from ollama_llm_bench.backend.core.models import EvalVerdict
from ollama_llm_bench.backend.utils.text_utils import parse_v2_judge_response


@pytest.mark.parametrize(
    "text,expected_verdict,expect_error",
    [
        ('{"verdict":"pass","score":0.9,"reasoning":"good"}', EvalVerdict.PASS, False),
        ('{"verdict":"fail","score":0.1,"reasoning":"bad"}', EvalVerdict.FAIL, False),
        ('{"verdict":"PASS","score":0.9,"reasoning":"ok"}', EvalVerdict.PASS, False),
        ('{"verdict":"FAIL","score":0.2,"reasoning":"nope"}', EvalVerdict.FAIL, False),
        ('```json\n{"verdict":"pass","score":0.9,"reasoning":"ok"}\n```', EvalVerdict.PASS, False),
        ('Here is the result: {"verdict":"pass","score":0.8,"reasoning":"OK"}', EvalVerdict.PASS, False),
        ('{"verdict":"pass","score":0.9,"reasoning":"He said \\"yes\\""}', EvalVerdict.PASS, False),
        ("", EvalVerdict.UNKNOWN, True),
        ("not json at all", EvalVerdict.UNKNOWN, True),
        ("(empty response)", EvalVerdict.UNKNOWN, True),
    ],
    ids=[
        "clean_json_pass",
        "clean_json_fail",
        "uppercase_pass",
        "uppercase_fail",
        "markdown_fence",
        "leading_prose",
        "escaped_quotes",
        "empty_string",
        "non_json",
        "empty_marker",
    ],
)
def test_parse_v2_judge_response_robustness(text: str, expected_verdict: EvalVerdict, expect_error: bool) -> None:
    has_error, verdict, score, reasoning = parse_v2_judge_response(text)
    assert verdict == expected_verdict
    assert has_error is expect_error
    if not expect_error:
        assert 0.0 <= score <= 1.0
        assert isinstance(reasoning, str)


def test_parse_v2_judge_response_truncated_json_repaired() -> None:
    """Partial JSON truncated at max_tokens boundary should be repaired and parsed."""
    # Truncated before closing brace — simulate max_tokens cutoff
    truncated = '{"verdict":"pass","score":0.9,"reasoning":"trunca'
    has_error, verdict, score, _ = parse_v2_judge_response(truncated)
    assert has_error is False
    assert verdict == EvalVerdict.PASS
    assert score == pytest.approx(0.9)


def test_parse_v2_judge_response_score_clamped() -> None:
    """Scores outside [0,1] must be clamped."""
    text = '{"verdict":"pass","score":1.5,"reasoning":"over"}'
    has_error, _, score, _ = parse_v2_judge_response(text)
    assert has_error is False
    assert score == pytest.approx(1.0)


def test_parse_v2_judge_response_unknown_verdict_returns_no_error() -> None:
    """An unknown verdict string parsed from valid JSON is not an error."""
    text = '{"verdict":"maybe","score":0.5,"reasoning":"unclear"}'
    has_error, verdict, _, _ = parse_v2_judge_response(text)
    assert has_error is False
    assert verdict == EvalVerdict.UNKNOWN


def test_parse_v2_judge_response_regex_branch_pass() -> None:
    """Regex branch correctly captures pass verdict when JSON parse fails but patterns are present."""
    # Embed verdict/score patterns in prose — JSON parse fails, regex succeeds
    prose_with_patterns = 'Analysis result: "verdict":"pass", "score":0.7 (assessment complete)'
    has_error, verdict, score, _ = parse_v2_judge_response(prose_with_patterns)
    assert has_error is False
    assert verdict == EvalVerdict.PASS
    assert score == pytest.approx(0.7)


def test_parse_v2_judge_response_regex_branch_fail() -> None:
    """Regex branch correctly captures fail verdict when JSON parse fails but patterns are present."""
    prose_with_patterns = 'Result: "verdict":"fail", "score":0.2 (evaluation done)'
    has_error, verdict, score, _ = parse_v2_judge_response(prose_with_patterns)
    assert has_error is False
    assert verdict == EvalVerdict.FAIL
    assert score == pytest.approx(0.2)
