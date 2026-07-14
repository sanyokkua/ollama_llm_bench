"""Proves: STORY-036-AC-5 — the omit-absent-field, unrecognized-verbosity, and
unrecognized-kind fallback behaviours, plus determinism and input immutability (§9)."""

from collections.abc import Callable
import copy
from typing import cast

import pytest

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import make_log_formatter

_LONG_TEXT = "The quick brown fox jumps over the lazy dog. " * 6


def _make_absent_field_event() -> RunLogEvent:
    return RunLogEvent(kind=RunLogEventKind.DONE, timestamp="2026-07-14T10:00:00Z")


def _make_long_prompt_event() -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.DONE, timestamp="2026-07-14T10:00:00Z", prompt_excerpt=_LONG_TEXT
    )


def _make_unrecognized_kind_event() -> RunLogEvent:
    return RunLogEvent(
        kind=cast("RunLogEventKind", "not_a_real_kind"), timestamp="2026-07-14T10:00:00Z"
    )


def _assert_field_omitted_with_no_placeholder(fragment: str) -> None:
    assert "ttft:" not in fragment
    assert fragment != ""


def _assert_unrecognized_verbosity_falls_back_to_normal(fragment: str) -> None:
    assert "…" in fragment
    assert _LONG_TEXT not in fragment
    assert fragment != ""


def _assert_unrecognized_kind_uses_generic_info_tag(fragment: str) -> None:
    assert '<span class="tone-info">EVENT</span>' in fragment


@pytest.mark.parametrize(
    ("build_event", "verbosity", "assert_fragment"),
    [
        (
            _make_absent_field_event,
            RunLogVerbosity.VERBOSE,
            _assert_field_omitted_with_no_placeholder,
        ),
        (
            _make_long_prompt_event,
            cast("RunLogVerbosity", "not_a_real_verbosity"),
            _assert_unrecognized_verbosity_falls_back_to_normal,
        ),
        (
            _make_unrecognized_kind_event,
            RunLogVerbosity.NORMAL,
            _assert_unrecognized_kind_uses_generic_info_tag,
        ),
    ],
    ids=["absent_field_omitted", "unrecognized_verbosity_as_normal", "unrecognized_kind_info_tag"],
)
def test_unrecognized_and_absent_field_fallbacks(
    build_event: Callable[[], RunLogEvent],
    verbosity: RunLogVerbosity,
    assert_fragment: Callable[[str], None],
) -> None:
    """Proves: STORY-036-AC-5

    Covers LF-16, LF-21, LF-22. A field selected by the verbosity but absent from the
    event's payload is omitted with no empty placeholder; an unrecognized `verbosity`
    value is treated as `NORMAL` and a line is still produced; an unrecognized event
    kind is rendered with the `info` tone and a generic tag.
    """
    formatter = make_log_formatter()
    event = build_event()

    # Act
    fragment = formatter.format_event(event=event, verbosity=verbosity)

    # Assert
    assert_fragment(fragment)


def test_formatting_is_deterministic() -> None:
    """Proves: STORY-036-AC-5

    Covers LF-23. The same `(event, verbosity)` pair produces a byte-identical fragment
    every time it is formatted.
    """
    formatter = make_log_formatter()
    event = RunLogEvent(
        kind=RunLogEventKind.RETRY,
        timestamp="2026-07-14T10:00:00Z",
        retry_attempt=2,
        retry_reason="Connection refused",
    )

    # Act
    first = formatter.format_event(event=event, verbosity=RunLogVerbosity.VERBOSE)
    second = formatter.format_event(event=event, verbosity=RunLogVerbosity.VERBOSE)

    # Assert
    assert first == second


def test_input_event_is_not_mutated_by_formatting() -> None:
    """Proves: STORY-036-AC-5

    Covers LF-25. Formatting an event leaves the input `RunLogEvent` unchanged.
    """
    formatter = make_log_formatter()
    event = RunLogEvent(
        kind=RunLogEventKind.JUDGE,
        timestamp="2026-07-14T10:00:00Z",
        judge_reasoning="The answer used a <table> instead of prose.",
    )
    snapshot = copy.deepcopy(event)

    # Act
    formatter.format_event(event=event, verbosity=RunLogVerbosity.VERBOSE)

    # Assert
    assert event == snapshot
