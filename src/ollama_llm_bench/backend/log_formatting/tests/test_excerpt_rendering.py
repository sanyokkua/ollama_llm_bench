"""Proves: STORY-036-AC-2 — prompt/response excerpt rendering varies by verbosity (§6.2, §6.4)."""

import re

import pytest

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import make_log_formatter
from ollama_llm_bench.backend.log_formatting._internal.excerpt import TRUNCATION_BUDGET_CHARS

_LONG_TEXT = "The quick brown fox jumps over the lazy dog. " * 6
_CHAR_COUNT = len(_LONG_TEXT)
_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|#x27);")


def _make_event() -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.DONE,
        timestamp="2026-07-14T10:00:00Z",
        prompt_excerpt=_LONG_TEXT,
        response_excerpt=_LONG_TEXT,
    )


@pytest.mark.parametrize(
    ("verbosity", "expect_ellipsis", "expect_full_text"),
    [
        (RunLogVerbosity.SHORT, False, False),
        (RunLogVerbosity.NORMAL, True, False),
        (RunLogVerbosity.VERBOSE, False, True),
    ],
    ids=["short_size_only", "normal_truncated_excerpt", "verbose_full_text"],
)
def test_prompt_response_rendering_per_verbosity(
    *, verbosity: RunLogVerbosity, expect_ellipsis: bool, expect_full_text: bool
) -> None:
    """Proves: STORY-036-AC-2

    Covers LF-19. At Short, the prompt/response fields show the character count only and
    never the raw text. At Normal, they show a truncated excerpt with a trailing ellipsis
    plus the character count, and never the full raw text. At Verbose, they show the full
    untruncated text plus the character count, with no ellipsis.
    """
    formatter = make_log_formatter()
    event = _make_event()

    # Act
    fragment = formatter.format_event(event=event, verbosity=verbosity)

    # Assert
    assert f"({_CHAR_COUNT} chars)" in fragment or f"{_CHAR_COUNT} chars" in fragment
    assert ("…" in fragment) is expect_ellipsis
    assert (_LONG_TEXT in fragment) is expect_full_text


_PROMPT_TOKEN_COUNT = 32
_COMPLETION_TOKEN_COUNT = 47


def _make_event_with_token_counts() -> RunLogEvent:
    return RunLogEvent(
        kind=RunLogEventKind.DONE,
        timestamp="2026-07-14T10:00:00Z",
        prompt_excerpt=_LONG_TEXT,
        response_excerpt=_LONG_TEXT,
        prompt_tokens=_PROMPT_TOKEN_COUNT,
        completion_tokens=_COMPLETION_TOKEN_COUNT,
    )


@pytest.mark.parametrize(
    ("verbosity", "expect_ellipsis", "expect_full_text"),
    [
        (RunLogVerbosity.SHORT, False, False),
        (RunLogVerbosity.NORMAL, True, False),
        (RunLogVerbosity.VERBOSE, False, True),
    ],
    ids=["short_size_only", "normal_truncated_excerpt", "verbose_full_text"],
)
def test_prompt_response_rendering_with_token_counts_per_verbosity(
    *, verbosity: RunLogVerbosity, expect_ellipsis: bool, expect_full_text: bool
) -> None:
    """Proves: STORY-036-AC-2

    Covers LF-1, LF-2, LF-3. When the event's transport reported token counts, the
    combined `"N chars, M tokens"` string is shown for both the prompt and response
    fields at every verbosity, alongside the size-only / truncated-excerpt / full-text
    rendering §6.2 prescribes for that verbosity — proving the token-count-present path
    of the format documented in STORY-036-AC-2's table, not just the char-only fallback.
    """
    formatter = make_log_formatter()
    event = _make_event_with_token_counts()

    # Act
    fragment = formatter.format_event(event=event, verbosity=verbosity)

    # Assert
    assert f"{_CHAR_COUNT} chars, {_PROMPT_TOKEN_COUNT} tokens" in fragment
    assert f"{_CHAR_COUNT} chars, {_COMPLETION_TOKEN_COUNT} tokens" in fragment
    assert ("…" in fragment) is expect_ellipsis
    assert (_LONG_TEXT in fragment) is expect_full_text


def test_prompt_response_rendering_without_token_counts_falls_back_to_char_only() -> None:
    """Proves: STORY-036-AC-2

    Given a prompt/response field whose event carries no token counts (the provider
    transport did not report usage), when the event is formatted, then the rendered
    counts string falls back to the character-count-only form with no `"tokens"`
    substring and no `None` placeholder anywhere in the fragment.
    """
    formatter = make_log_formatter()
    event = _make_event()

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert
    assert f"{_CHAR_COUNT} chars" in fragment
    assert "tokens" not in fragment
    assert "None" not in fragment


def test_truncation_never_splits_an_escaped_entity() -> None:
    """Proves: STORY-036-AC-2

    Covers LF-20. Given a Normal-verbosity prompt whose escaped form places an `&...;`
    HTML entity straddling the fixed truncation budget, when the event is formatted, then
    the escape-before-truncate ordering (§6.4) means the fragment never contains a split
    entity — every `&` in the output is part of a complete, well-formed entity.
    """
    # Arrange — an `&` positioned so its escaped `&amp;` form straddles the truncation cut.
    straddle_offset = TRUNCATION_BUDGET_CHARS - 3
    raw_text = ("x" * straddle_offset) + "&entities must never be split by truncation" * 3
    formatter = make_log_formatter()
    event = RunLogEvent(
        kind=RunLogEventKind.DONE, timestamp="2026-07-14T10:00:00Z", prompt_excerpt=raw_text
    )

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert — removing every complete, well-formed entity must leave no stray `&`.
    assert "&" not in _ENTITY_RE.sub("", fragment)
