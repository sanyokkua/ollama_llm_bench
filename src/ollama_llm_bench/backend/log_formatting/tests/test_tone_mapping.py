"""Proves: STORY-036-AC-3 — each RunLogEventKind maps to exactly its §6.3 tone class."""

import pytest

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import make_log_formatter


@pytest.mark.parametrize(
    ("kind", "expected_tone"),
    [
        (RunLogEventKind.STAGE, "info"),
        (RunLogEventKind.SYSTEM, "info"),
        (RunLogEventKind.PROVIDER_SWITCH, "info"),
        (RunLogEventKind.MODEL_SWITCH, "info"),
        (RunLogEventKind.TASK_START, "primary"),
        (RunLogEventKind.DONE, "success"),
        (RunLogEventKind.FINISHED, "success"),
        (RunLogEventKind.JUDGE, "warning"),
        (RunLogEventKind.RETRY, "error"),
        (RunLogEventKind.FAILED, "error"),
        (RunLogEventKind.STOPPED, "muted"),
    ],
    ids=[
        "stage_info",
        "system_info",
        "provider_switch_info",
        "model_switch_info",
        "task_start_primary",
        "done_success",
        "finished_success",
        "judge_warning",
        "retry_error",
        "failed_error",
        "stopped_muted",
    ],
)
def test_event_kind_maps_to_tone(*, kind: RunLogEventKind, expected_tone: str) -> None:
    """Proves: STORY-036-AC-3

    Covers LF-5..LF-10. Each of the eleven `RunLogEventKind` members wraps its kind tag
    in a span carrying exactly the tone class the §6.3 table declares — never a raw
    colour value.
    """
    formatter = make_log_formatter()
    event = RunLogEvent(kind=kind, timestamp="2026-07-14T10:00:00Z")

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert
    assert f'class="tone-{expected_tone}"' in fragment


def test_task_judge_timeout_kind_maps_to_error_tone() -> None:
    """Proves: STORY-060-AC-1

    Covers EC-PROV-4a: the ``task_judge_timeout`` kind (added by STORY-060 for the
    per-task judge-call-exhaustion log line) wraps its kind tag in the same
    ``error`` tone as ``retry``/``failed``.
    """
    formatter = make_log_formatter()
    event = RunLogEvent(kind=RunLogEventKind.TASK_JUDGE_TIMEOUT, timestamp="2026-07-14T10:00:00Z")

    # Act
    fragment = formatter.format_event(event=event, verbosity=RunLogVerbosity.NORMAL)

    # Assert
    assert 'class="tone-error"' in fragment
