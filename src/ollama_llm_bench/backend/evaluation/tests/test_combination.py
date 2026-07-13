"""Tests for backend/evaluation/_internal/combination.py (§6.6 of
04_EVALUATION_PIPELINE.md; §11 of 08-P_judge_protocol.md)."""

import pytest

from ollama_llm_bench.backend.domain import ResolutionLayer, Verdict
from ollama_llm_bench.backend.evaluation._internal.combination import combine_verdict_impl


@pytest.mark.parametrize(
    (
        "sanity_check_passed",
        "keyword_verdict",
        "cosine_verdict",
        "judge_enabled",
        "judge_verdict",
        "force_judge_on_prior_failure",
        "expected_verdict",
        "expected_layer",
    ),
    [
        # Sanity fails: always final, judge irrelevant.
        (
            False,
            Verdict.PASS,
            Verdict.PASS,
            True,
            Verdict.PASS,
            True,
            Verdict.FAIL,
            ResolutionLayer.KEYWORD,
        ),
        # Keyword-only enabled.
        (True, Verdict.PASS, None, False, None, False, Verdict.PASS, ResolutionLayer.KEYWORD),
        (True, Verdict.FAIL, None, False, None, False, Verdict.FAIL, ResolutionLayer.KEYWORD),
        # Keyword + cosine, judge disabled: keyword FAIL short-circuits.
        (
            True,
            Verdict.FAIL,
            Verdict.PASS,
            False,
            None,
            False,
            Verdict.FAIL,
            ResolutionLayer.KEYWORD,
        ),
        # Keyword + cosine, judge disabled: keyword PASS, cosine decides.
        (
            True,
            Verdict.PASS,
            Verdict.FAIL,
            False,
            None,
            False,
            Verdict.FAIL,
            ResolutionLayer.COSINE,
        ),
        # Keyword + cosine, judge disabled, cosine skipped for task type: keyword decides.
        (True, Verdict.PASS, None, False, None, False, Verdict.PASS, ResolutionLayer.KEYWORD),
        # Judge enabled, force-judge off, keyword FAIL stands even though judge says PASS.
        (
            True,
            Verdict.FAIL,
            Verdict.FAIL,
            True,
            Verdict.PASS,
            False,
            Verdict.FAIL,
            ResolutionLayer.KEYWORD,
        ),
        # Judge enabled, force-judge off, keyword PASS: judge decides.
        (
            True,
            Verdict.PASS,
            Verdict.PASS,
            True,
            Verdict.FAIL,
            False,
            Verdict.FAIL,
            ResolutionLayer.JUDGE,
        ),
        # Judge enabled, force-judge on: judge decides even over a keyword FAIL.
        (
            True,
            Verdict.FAIL,
            Verdict.FAIL,
            True,
            Verdict.PASS,
            True,
            Verdict.PASS,
            ResolutionLayer.JUDGE,
        ),
        # Judge enabled, transport failure (judge_verdict=None), keyword PASS: falls back to cosine.
        (True, Verdict.PASS, Verdict.FAIL, True, None, False, Verdict.FAIL, ResolutionLayer.COSINE),
        # Judge enabled, transport failure, no cosine: falls back to keyword.
        (True, Verdict.PASS, None, True, None, False, Verdict.PASS, ResolutionLayer.KEYWORD),
    ],
)
def test_verdict_combination_cascade(  # noqa: PLR0913  # one parametrize column per
    # combination-cascade input plus the two expected outputs; AC-7's table is inherently
    # this wide and splitting it would obscure the row-to-assertion mapping
    *,
    sanity_check_passed: bool,
    keyword_verdict: Verdict | None,
    cosine_verdict: Verdict | None,
    judge_enabled: bool,
    judge_verdict: Verdict | None,
    force_judge_on_prior_failure: bool,
    expected_verdict: Verdict,
    expected_layer: ResolutionLayer,
) -> None:
    """Proves: STORY-028-AC-7

    Every combination-cascade row produces the documented verdict and
    resolution_layer.
    """
    result = combine_verdict_impl(
        sanity_check_passed=sanity_check_passed,
        keyword_verdict=keyword_verdict,
        cosine_verdict=cosine_verdict,
        judge_enabled=judge_enabled,
        judge_verdict=judge_verdict,
        force_judge_on_prior_failure=force_judge_on_prior_failure,
    )

    assert result.verdict == expected_verdict
    assert result.resolution_layer == expected_layer
