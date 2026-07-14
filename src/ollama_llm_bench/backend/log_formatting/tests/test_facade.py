"""Proves the module's public surface is importable and the factory/fake both work cleanly."""

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import LogFormatter, make_log_formatter
from ollama_llm_bench.backend.log_formatting.testing import FakeLogFormatter


def test_make_log_formatter_returns_a_protocol_conforming_instance_that_formats_one_line() -> None:
    """Constructing via `make_log_formatter()` and formatting a minimal event returns a
    non-empty, single-line string."""
    formatter: LogFormatter = make_log_formatter()
    event = RunLogEvent(kind=RunLogEventKind.STAGE, timestamp="2026-07-14T10:00:00Z")

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert
    assert fragment != ""
    assert "\n" not in fragment


def test_fake_log_formatter_records_calls_and_returns_the_canned_fragment() -> None:
    """`FakeLogFormatter` records every `(event, verbosity)` call and returns the canned,
    settable fragment for downstream-consumer tests."""
    fake = FakeLogFormatter()
    event = RunLogEvent(kind=RunLogEventKind.DONE, timestamp="2026-07-14T10:00:00Z")
    fake.next_fragment = '<span class="tone-success">DONE</span>'

    # Act
    result = fake.format_event(event=event, verbosity=RunLogVerbosity.SHORT)

    # Assert
    assert result == '<span class="tone-success">DONE</span>'
    assert fake.calls == [(event, RunLogVerbosity.SHORT)]
