"""Attempts/error/performance section coverage tests (`20_HTML_RENDERING.md` §6.1, HR-03/04/05/11)."""

import msgspec
import pytest

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResultAttempt,
    ErrorKind,
    RunMode,
)
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)

_ATTEMPTS_TABLE_MARKER = "Timeout (ms)"
_DASH = "—"

_ONE_SUCCESSFUL_ATTEMPT = (
    BenchmarkResultAttempt(
        attempt_index=1, timeout_ms=30000, duration_ms=500, outcome=AttemptOutcome.SUCCESS
    ),
)
_TWO_SUCCESSFUL_ATTEMPTS = (
    BenchmarkResultAttempt(
        attempt_index=1, timeout_ms=30000, duration_ms=None, outcome=AttemptOutcome.TIMEOUT
    ),
    BenchmarkResultAttempt(
        attempt_index=2, timeout_ms=45000, duration_ms=700, outcome=AttemptOutcome.SUCCESS
    ),
)
_ONE_FAILED_ATTEMPT = (
    BenchmarkResultAttempt(
        attempt_index=1,
        timeout_ms=30000,
        duration_ms=200,
        outcome=AttemptOutcome.ERROR,
        error_kind=ErrorKind.PROVIDER,
        error_message="connection reset",
    ),
)


@pytest.mark.parametrize(
    "attempts,expect_shown",
    [
        (_ONE_SUCCESSFUL_ATTEMPT, False),
        (_TWO_SUCCESSFUL_ATTEMPTS, True),
        (_ONE_FAILED_ATTEMPT, True),
    ],
    ids=["single-success-omitted", "multi-attempt-shown", "single-non-success-shown"],
)
def test_attempts_section_visibility_follows_the_omission_rule(
    attempts: tuple[BenchmarkResultAttempt, ...],
    expect_shown: bool,  # noqa: FBT001  # pytest.mark.parametrize table column, not a call-site flag
) -> None:
    """Proves: STORY-032 coverage — the attempts section is rendered and lists
    every attempt when there is more than one attempt or any attempt did not
    succeed, and is omitted entirely for exactly one successful attempt.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    result = msgspec.structs.replace(base_result, attempts=attempts)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert (_ATTEMPTS_TABLE_MARKER in fragment) is expect_shown


def test_error_section_shows_escaped_message_verbatim_when_error_fields_set() -> None:
    """Proves: STORY-032 coverage — the error section appears and renders the
    escaped error message verbatim (no linebreak-to-`<br>` transformation)
    when error_kind/error_message are set.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    result = msgspec.structs.replace(
        base_result,
        error_kind=ErrorKind.TIMEOUT,
        error_message="Timed out after <5s> & retrying\nSecond line",
    )
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Error kind: timeout" in fragment
    assert "Timed out after &lt;5s&gt; &amp; retrying\nSecond line" in fragment
    assert "<br>" not in fragment


def test_error_section_omitted_when_no_error_fields_set() -> None:
    """Proves: STORY-032 coverage — the error section is omitted entirely when
    neither error_kind nor error_message is set.
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Error kind:" not in fragment


def test_performance_section_renders_full_numeric_metrics() -> None:
    """Proves: STORY-032 coverage — the performance section appears and renders
    real numeric metric values when populated.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    result = msgspec.structs.replace(
        base_result,
        ttft_ms=1234,
        total_time_ms=5678,
        tokens_per_second=12.345,
        prompt_tokens=100,
        completion_tokens=50,
    )
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "TTFT (s): 1.234" in fragment
    assert "Total time (s): 5.678" in fragment
    assert "Tokens/second: 12.35" in fragment
    assert "Prompt tokens: 100" in fragment
    assert "Response tokens: 50" in fragment


def test_performance_section_renders_dash_for_one_unset_metric_without_omitting_section() -> None:
    """Proves: STORY-032 coverage — an individual `None` metric within an
    otherwise-populated performance section renders as a dash, without the
    whole section being omitted.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    result = msgspec.structs.replace(base_result, ttft_ms=1234, prompt_tokens=None)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "TTFT (s): 1.234" in fragment
    assert f"Prompt tokens: {_DASH}" in fragment
