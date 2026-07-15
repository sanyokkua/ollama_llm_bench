"""Colocated tests for the full-Verbose run-log-file event formatter — STORY-037-AC-1."""

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, Verdict
from ollama_llm_bench.backend.log_file_writer._internal.verbose_formatter import (
    format_verbose_line,
)

_FULLY_POPULATED_EVENT = RunLogEvent(
    kind=RunLogEventKind.DONE,
    timestamp="2026-05-22T14:53:27Z",
    provider_id="ollama_local",
    model_name="llama3.2:3b",
    task_id="coding_java_two_sum",
    stage="benchmarking",
    started_at="2026-05-22T14:53:25Z",
    finished_at="2026-05-22T14:53:27Z",
    total_time_ms=2140,
    ttft_ms=310,
    tokens_per_second=42.5,
    prompt_tokens=120,
    completion_tokens=188,
    prompt_excerpt="What is 2 + 2?",
    response_excerpt="4",
    retry_attempt=2,
    retry_reason="Connection refused",
    error_text="none",
    judge_verdict=Verdict.PASS,
    judge_reasoning="Correct answer.",
)

_MINIMAL_EVENT = RunLogEvent(
    kind=RunLogEventKind.STAGE,
    timestamp="2026-05-22T14:53:27Z",
)


def test_fully_populated_event_renders_every_field_name() -> None:
    """Proves: STORY-037-AC-1

    A fully populated ``RunLogEvent`` renders every Verbose-density field name in the
    line — the per-run file always records the full field set regardless of any
    on-screen verbosity setting (there is none on this formatter, which is the point).
    """
    line = format_verbose_line(_FULLY_POPULATED_EVENT)

    for field_name in (
        "provider_id",
        "model_name",
        "task_id",
        "stage",
        "started_at",
        "finished_at",
        "total_time_ms",
        "ttft_ms",
        "tokens_per_second",
        "prompt_tokens",
        "completion_tokens",
        "prompt_excerpt",
        "response_excerpt",
        "retry_attempt",
        "retry_reason",
        "error_text",
        "judge_verdict",
        "judge_reasoning",
    ):
        assert f"{field_name}=" in line


def test_minimal_event_omits_absent_optional_fields() -> None:
    """Proves: STORY-037-AC-1

    An event carrying only the required ``kind``/``timestamp`` fields renders no
    optional-field placeholder — an absent field is skipped entirely, never rendered
    as an empty value.
    """
    line = format_verbose_line(_MINIMAL_EVENT)

    assert line == "2026-05-22T14:53:27Z stage"


def test_embedded_newline_in_excerpt_collapses_to_one_physical_line() -> None:
    """Proves: STORY-037-AC-1

    A newline embedded in ``response_excerpt`` is replaced with a space so the whole
    record stays exactly one physical line on disk.
    """
    event = RunLogEvent(
        kind=RunLogEventKind.DONE,
        timestamp="2026-05-22T14:53:27Z",
        response_excerpt="line one\nline two\r\nline three",
    )

    line = format_verbose_line(event)

    assert "\n" not in line
    assert "\r" not in line
    assert "response_excerpt=line one line two line three" in line
