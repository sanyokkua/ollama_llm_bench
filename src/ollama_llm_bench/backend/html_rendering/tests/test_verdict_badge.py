"""Header verdict-badge rendering coverage tests (`20_HTML_RENDERING.md` §6.1, HR-19)."""

import msgspec
import pytest

from ollama_llm_bench.backend.domain import ResultStatus, RunMode, Verdict
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)

_BADGE_STYLE_MARKER = "border-radius:4px;font-weight:600;"


@pytest.mark.parametrize(
    "verdict,status,expected_label",
    [
        (Verdict.PASS, ResultStatus.COMPLETED, "PASS"),
        (Verdict.FAIL, ResultStatus.COMPLETED, "FAIL"),
        (None, ResultStatus.ERRORED, "ERROR"),
    ],
    ids=["pass", "fail", "terminal-failure-no-verdict"],
)
def test_verdict_badge_renders_expected_label(
    verdict: Verdict | None, status: ResultStatus, expected_label: str
) -> None:
    """Proves: STORY-032 coverage — the GRADED-mode header verdict badge renders
    PASS/FAIL for a set Verdict and the render-only ERROR token for a
    terminal-failure status carrying no verdict.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id, status=status)
    result = msgspec.structs.replace(base_result, verdict=verdict)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.GRADED)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert f">{expected_label}</span>" in fragment
    assert _BADGE_STYLE_MARKER in fragment


def test_synthetic_result_with_no_verdict_shows_no_badge() -> None:
    """Proves: STORY-032 coverage — a SYNTHETIC-mode result carrying no verdict
    and no terminal-failure status shows no verdict badge at all (§10.3).
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id, status=ResultStatus.COMPLETED)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.SYNTHETIC)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert _BADGE_STYLE_MARKER not in fragment
