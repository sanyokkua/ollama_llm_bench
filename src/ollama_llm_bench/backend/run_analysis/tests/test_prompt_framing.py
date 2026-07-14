"""Proves: STORY-035-AC-6"""

import pytest

from ollama_llm_bench.backend.domain import ChatRole, ResponseFormat, RunMode
from ollama_llm_bench.backend.run_analysis._internal.aggregation import RunDigest, RunFacts
from ollama_llm_bench.backend.run_analysis._internal.prompt import build_analysis_request


def _make_minimal_digest(run_mode: RunMode) -> RunDigest:
    return RunDigest(
        facts=RunFacts(
            run_mode=run_mode,
            test_model_labels=("p1/m1",),
            judge_model_label="none",
            embedding_model_label="none",
            started_at=None,
            finished_at=None,
            total_elapsed_ms=0,
            total_tasks=0,
            completed_tasks=0,
        ),
        per_model=(),
        per_category=(),
        notable_results=(),
    )


@pytest.mark.parametrize(
    ("run_mode", "expected_fragment"),
    [
        (RunMode.GRADED, "pass rate"),
        (RunMode.TASKS, "throughput"),
        (RunMode.SYNTHETIC, "input/output size"),
    ],
)
def test_mode_aware_framing_and_single_call(run_mode: RunMode, expected_fragment: str) -> None:
    """Proves: STORY-035-AC-6

    GRADED/TASKS/SYNTHETIC each produce a distinct framing line in the user
    message; response_format is TEXT; exactly one ChatRequest is built per call.
    Covers RA-03, RA-09, RA-12.
    """
    digest = _make_minimal_digest(run_mode)
    request = build_analysis_request(digest, run_mode=run_mode, model_name="m1", timeout_ms=20_000)
    assert request.response_format == ResponseFormat.TEXT
    assert request.messages[0].role == ChatRole.SYSTEM
    assert request.messages[-1].role == ChatRole.USER
    assert expected_fragment in request.messages[-1].content.lower()
