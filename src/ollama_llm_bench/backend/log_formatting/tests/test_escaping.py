"""Proves: STORY-036-AC-4 — HTML escaping and newline normalization keep the line safe and flat."""

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import make_log_formatter

_BLOCK_LEVEL_TAGS = ("<div", "<p>", "<p ", "<table", "<ul", "<ol", "<section", "<article")


def test_escaping_and_newline_normalization_one_line() -> None:
    """Proves: STORY-036-AC-4

    Covers LF-17, LF-18, LF-26. Given an event whose model response and error text each
    contain `<`, `>`, `&`, `"`, and a newline, when it is formatted, then all four
    characters are escaped to HTML entities in both fields, every newline is replaced
    with a single space, and the fragment contains no newline and no block-level HTML
    element.
    """
    # Arrange
    response_raw = 'Result: <b>"bold"</b> & more\nsecond line'
    error_raw = 'Connection failed: "timeout" & retry\nsecond line of error'
    formatter = make_log_formatter()
    event = RunLogEvent(
        kind=RunLogEventKind.FAILED,
        timestamp="2026-07-14T10:00:00Z",
        response_excerpt=response_raw,
        error_text=error_raw,
    )

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert — newline normalization: the fragment is one logical line.
    assert "\n" not in fragment
    assert "\r" not in fragment

    # Assert — HTML escaping: raw markup is gone, entities are present.
    assert "<b>" not in fragment
    assert "</b>" not in fragment
    assert '"bold"' not in fragment
    assert '"timeout"' not in fragment
    assert "&lt;b&gt;" in fragment
    assert "&lt;/b&gt;" in fragment
    assert "&quot;bold&quot;" in fragment
    assert "&quot;timeout&quot;" in fragment
    assert fragment.count("&amp;") >= 2  # noqa: PLR2004  # one "&" in each of response/error

    # Assert — no block-level element is present; only the trusted inline `<span>` markup.
    lowered = fragment.lower()
    for block_tag in _BLOCK_LEVEL_TAGS:
        assert block_tag not in lowered
