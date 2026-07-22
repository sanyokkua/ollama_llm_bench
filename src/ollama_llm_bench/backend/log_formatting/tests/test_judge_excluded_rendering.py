"""Acceptance tests for STORY-073: `judge_excluded` rendering (description.md §8.3)."""

import pytest

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import make_log_formatter

_CANONICAL = (
    "Judge model 'Local Ollama' excluded: 3 consecutive max-budget timeouts. "
    "Remaining tasks' judge phase will be skipped."
)


def _judge_excluded_event(*, provider_name: str | None = "Local Ollama") -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.JUDGE_EXCLUDED,
        timestamp="2026-07-22T10:00:00+00:00",
        provider_id="0b6f9a2e-3c41-4b7e-9f1d-2a5c8e7d4f10",
        model_name="qwen3:8b",
        provider_name=provider_name,
        consecutive_timeouts=3,
    )


def test_judge_excluded_kind_renders_error_tone() -> None:
    """Proves: STORY-073-AC-2

    The `judge_excluded` kind carries the `error` tone class on its kind tag.
    """
    fragment = make_log_formatter().format_event(
        event=_judge_excluded_event(), verbosity=RunLogVerbosity.NORMAL
    )
    assert 'class="tone-error"' in fragment


@pytest.mark.parametrize(
    "verbosity", [RunLogVerbosity.SHORT, RunLogVerbosity.NORMAL, RunLogVerbosity.VERBOSE]
)
def test_judge_excluded_renders_canonical_text_at_every_verbosity(
    verbosity: RunLogVerbosity,
) -> None:
    """Proves: STORY-073-AC-1

    The canonical §8.3 sentence renders with the provider display name and the
    consecutive-timeout count, independent of the verbosity field selection.
    """
    fragment = make_log_formatter().format_event(event=_judge_excluded_event(), verbosity=verbosity)
    assert _CANONICAL in fragment


def test_judge_excluded_escapes_untrusted_provider_name() -> None:
    """Proves: STORY-073-AC-2

    A provider display name containing markup is HTML-escaped before it is
    placed in the fragment (15_LOG_FORMATTING.md §6.4).
    """
    fragment = make_log_formatter().format_event(
        event=_judge_excluded_event(provider_name="<b>Evil</b>"), verbosity=RunLogVerbosity.NORMAL
    )
    assert "<b>" not in fragment
    assert "&lt;b&gt;Evil&lt;/b&gt;" in fragment
