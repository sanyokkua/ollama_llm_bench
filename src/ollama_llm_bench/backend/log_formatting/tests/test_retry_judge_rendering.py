"""Retry- and judge-field per-verbosity rendering content (§6.2, §11.2, §11.3, #12-test-cases).

Covers LF-11..LF-15. Neither STORY-036-AC-1 (field-set nesting) nor STORY-036-AC-2
(prompt/response rendering) names retry/judge field *content* specifically, so these tests
carry a plain descriptive docstring rather than a `Proves:` line.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity, Verdict
from ollama_llm_bench.backend.log_formatting import make_log_formatter

_RETRY_ATTEMPT = 2
_RETRY_REASON = "Connection refused"
_JUDGE_REASONING = "The answer used a correct time complexity and clear explanation."


def _make_retry_event() -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.RETRY,
        timestamp="2026-07-14T10:00:00Z",
        retry_attempt=_RETRY_ATTEMPT,
        retry_reason=_RETRY_REASON,
    )


def _make_judge_event() -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.JUDGE,
        timestamp="2026-07-14T10:00:00Z",
        judge_verdict=Verdict.PASS,
        judge_reasoning=_JUDGE_REASONING,
    )


def _assert_retry_short_shows_attempt_count_only(fragment: str) -> None:
    assert f"attempts: {_RETRY_ATTEMPT}" in fragment
    assert "reason:" not in fragment
    assert _RETRY_REASON not in fragment


def _assert_retry_normal_shows_reason_only(fragment: str) -> None:
    assert f"retry: {_RETRY_REASON}" in fragment
    assert "attempts:" not in fragment


def _assert_retry_verbose_shows_attempts_and_reason(fragment: str) -> None:
    assert f"attempts: {_RETRY_ATTEMPT} · reason: {_RETRY_REASON}" in fragment


@pytest.mark.parametrize(
    ("verbosity", "assert_fragment"),
    [
        (RunLogVerbosity.SHORT, _assert_retry_short_shows_attempt_count_only),
        (RunLogVerbosity.NORMAL, _assert_retry_normal_shows_reason_only),
        (RunLogVerbosity.VERBOSE, _assert_retry_verbose_shows_attempts_and_reason),
    ],
    ids=["short_count_only", "normal_reason_only", "verbose_attempts_and_reason"],
)
def test_retry_field_rendering_per_verbosity(
    verbosity: RunLogVerbosity, assert_fragment: Callable[[str], None]
) -> None:
    """Covers LF-11, LF-12, LF-13 (§6.2, §11.2).

    A `RETRY` event's retry field shows the attempt count only at Short, the reason
    only at Normal, and both the attempts and the reason at Verbose.
    """
    formatter = make_log_formatter()
    event = _make_retry_event()

    # Act
    fragment = formatter.format_event(event=event, verbosity=verbosity)

    # Assert
    assert_fragment(fragment)


def _assert_judge_short_shows_verdict_only(fragment: str) -> None:
    assert "verdict: PASS" in fragment
    assert "reasoning:" not in fragment
    assert _JUDGE_REASONING not in fragment


def _assert_judge_shows_verdict_and_reasoning(fragment: str) -> None:
    assert f"verdict: PASS · reasoning: {_JUDGE_REASONING}" in fragment


@pytest.mark.parametrize(
    ("verbosity", "assert_fragment"),
    [
        (RunLogVerbosity.SHORT, _assert_judge_short_shows_verdict_only),
        (RunLogVerbosity.NORMAL, _assert_judge_shows_verdict_and_reasoning),
        (RunLogVerbosity.VERBOSE, _assert_judge_shows_verdict_and_reasoning),
    ],
    ids=["short_verdict_only", "normal_verdict_and_reasoning", "verbose_verdict_and_reasoning"],
)
def test_judge_field_rendering_per_verbosity(
    verbosity: RunLogVerbosity, assert_fragment: Callable[[str], None]
) -> None:
    """Covers LF-14, LF-15 (§6.2, §11.3).

    A `JUDGE` event's judge field shows the binary verdict only at Short, and the
    verdict plus the one-sentence reasoning at both Normal and Verbose — never a
    numeric score, since the judge produces no numeric score anywhere in the app.
    """
    formatter = make_log_formatter()
    event = _make_judge_event()

    # Act
    fragment = formatter.format_event(event=event, verbosity=verbosity)

    # Assert
    assert_fragment(fragment)


def test_judge_field_omitted_when_verdict_absent() -> None:
    """A `JUDGE`-kind event with no `judge_verdict` set omits the judge field entirely
    (§9's omit-absent-field fallback applied to the judge field specifically).
    """
    formatter = make_log_formatter()
    event = RunLogEvent(kind=RunLogEventKind.JUDGE, timestamp="2026-07-14T10:00:00Z")

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.VERBOSE)

    # Assert
    assert "verdict:" not in fragment
