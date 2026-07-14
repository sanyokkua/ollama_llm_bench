"""`render_log_line` coverage tests (`20_HTML_RENDERING.md` §6.2, HR-12/13/14)."""

import pytest

from ollama_llm_bench.backend.html_rendering import LogEntry, LogSeverity, make_result_html_renderer
from ollama_llm_bench.backend.html_rendering.tests.conftest import make_provider_id

_CHIP_STYLE_MARKER = "border-radius:3px;padding:0 4px;"
_RAW_MESSAGE = "build <ok> & done"
_ESCAPED_MESSAGE = "build &lt;ok&gt; &amp; done"
_EXPECTED_CHIP_COUNT = 3


def _make_log_entry(*, severity: LogSeverity, with_chips: bool) -> LogEntry:
    """Build a `LogEntry` fixture, optionally with all three optional chips set."""
    return LogEntry(
        timestamp="2026-05-16T15:00:00Z",
        severity=severity,
        message=_RAW_MESSAGE,
        provider_id=make_provider_id() if with_chips else None,
        model_name="llama3.2:3b" if with_chips else None,
        task_id="factual_capitals_france" if with_chips else None,
    )


@pytest.mark.parametrize(
    "severity",
    [LogSeverity.INFO, LogSeverity.ERROR],
    ids=["info", "error"],
)
def test_render_log_line_with_all_chips_set_shows_three_chips(severity: LogSeverity) -> None:
    """Proves: STORY-032 coverage — render_log_line renders all three optional
    chips (provider/model/task) and escapes the message when
    provider_id/model_name/task_id are all set, across log severities.
    """
    entry = _make_log_entry(severity=severity, with_chips=True)
    renderer = make_result_html_renderer()

    fragment = renderer.render_log_line(entry)

    assert fragment.count(_CHIP_STYLE_MARKER) == _EXPECTED_CHIP_COUNT
    assert severity.value.upper() in fragment
    assert _ESCAPED_MESSAGE in fragment
    assert _RAW_MESSAGE not in fragment


def test_render_log_line_with_no_chips_set_omits_all_three_chips() -> None:
    """Proves: STORY-032 coverage — render_log_line omits all three optional
    chips when provider_id/model_name/task_id are all `None`.
    """
    entry = _make_log_entry(severity=LogSeverity.DEBUG, with_chips=False)
    renderer = make_result_html_renderer()

    fragment = renderer.render_log_line(entry)

    assert fragment.count(_CHIP_STYLE_MARKER) == 0
