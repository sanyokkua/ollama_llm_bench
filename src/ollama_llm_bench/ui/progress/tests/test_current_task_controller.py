"""Colocated ``CurrentTaskController`` tests for ``ui/progress/`` (STORY-059)."""

import pytest

from ollama_llm_bench.backend.domain import InferenceContext
from ollama_llm_bench.ui.progress._internal.select import (
    accepts_progress_context,
    format_inference_generating_label,
    format_inference_waiting_label,
    format_judge_receiving_label,
    format_judge_waiting_label,
    format_retry_label,
)


@pytest.mark.parametrize(
    ("context", "accepted"),
    [
        (InferenceContext.BENCHMARK_TASK, True),
        (InferenceContext.BENCHMARK_JUDGE, True),
        (InferenceContext.RUN_ANALYSIS, False),
        (InferenceContext.PROVIDER_TEST, False),
    ],
    ids=[
        c.value
        for c, _accepted in [
            (InferenceContext.BENCHMARK_TASK, True),
            (InferenceContext.BENCHMARK_JUDGE, True),
            (InferenceContext.RUN_ANALYSIS, False),
            (InferenceContext.PROVIDER_TEST, False),
        ]
    ],
)
def test_progress_context_filter(context: InferenceContext, accepted: bool) -> None:  # noqa: FBT001
    """Proves: STORY-059-AC-3

    Covers EC-RUN-23's premise: only BENCHMARK_TASK/BENCHMARK_JUDGE are ever
    accepted by the Current-task controller; RUN_ANALYSIS/PROVIDER_TEST are
    routed to other widgets and must be rejected here.
    """
    assert accepts_progress_context(context) is accepted


def test_format_inference_waiting_label_renders_seconds_with_one_decimal() -> None:
    assert format_inference_waiting_label(1200) == "Waiting for first token — 1.2 s"


def test_format_inference_generating_label_marks_heuristic_estimate() -> None:
    """Proves: STORY-059-AC-6

    Covers EC-RUN-17: a heuristic-sourced token count is prefixed with ``~``.
    """
    label = format_inference_generating_label(tokens=184, elapsed_ms=4600, is_estimate=True)
    assert label == "Generating — ~184 tokens · 4.6 s elapsed"


def test_format_inference_generating_label_omits_marker_for_exact_count() -> None:
    label = format_inference_generating_label(tokens=184, elapsed_ms=5600, is_estimate=False)
    assert label == "Generating — 184 tokens · 5.6 s elapsed"


def test_format_judge_waiting_label_renders_seconds_with_one_decimal() -> None:
    assert format_judge_waiting_label(2400) == "Judge: waiting for response — 2.4 s"


def test_format_judge_receiving_label_marks_heuristic_estimate() -> None:
    label = format_judge_receiving_label(tokens=96, elapsed_ms=3100, is_estimate=True)
    assert label == "Judge: receiving — ~96 tokens · 3.1 s elapsed"


def test_format_retry_label_renders_attempt_over_total_and_reason() -> None:
    """Proves: STORY-059-AC-5"""
    assert format_retry_label(attempt=2, total_attempts=3, reason="Connection refused") == (
        "2/3 - Connection refused"
    )
