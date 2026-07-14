"""Proves: STORY-035-AC-1"""

import pytest

from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome, RunAnalysisResult


@pytest.mark.parametrize(
    ("outcome", "markdown", "error", "valid"),
    [
        (RunAnalysisOutcome.GENERATED, "# Overview\n...", None, True),
        (RunAnalysisOutcome.GENERATED, None, None, False),
        (RunAnalysisOutcome.SKIPPED, None, None, True),
        (RunAnalysisOutcome.SKIPPED, "should not be here", None, False),
        (RunAnalysisOutcome.FAILED, None, "judge_timeout_exhausted: ...", True),
        (RunAnalysisOutcome.FAILED, "should not be here", "reason", False),
    ],
)
def test_result_field_invariant_per_outcome(
    outcome: RunAnalysisOutcome, markdown: str | None, error: str | None, *, valid: bool
) -> None:
    """Proves: STORY-035-AC-1

    `outcome` is exactly one of GENERATED/SKIPPED/FAILED; `run_analysis_markdown` is
    non-None only on GENERATED; `error_message` is non-None only on FAILED. Covers RA-17.
    """
    result = RunAnalysisResult(outcome=outcome, run_analysis_markdown=markdown, error_message=error)
    matches_generated = (
        outcome == RunAnalysisOutcome.GENERATED and result.run_analysis_markdown is not None
    )
    matches_skipped_or_failed = (
        outcome != RunAnalysisOutcome.GENERATED and result.run_analysis_markdown is None
    )
    assert (matches_generated or matches_skipped_or_failed) == valid
