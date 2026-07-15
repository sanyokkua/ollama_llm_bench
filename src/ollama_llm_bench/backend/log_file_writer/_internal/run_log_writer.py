"""The per-run event-log writer implementation (STORY-037-AC-1).

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §4.2 — a
run log is never rotated; it is bounded by the run's task count and closed when the run
reaches a terminal state.
"""

from pathlib import Path

from ollama_llm_bench.backend.domain import RunLogEvent
from ollama_llm_bench.backend.log_file_writer._internal.safe_append import append_line_safely
from ollama_llm_bench.backend.log_file_writer._internal.verbose_formatter import (
    format_verbose_line,
)
from ollama_llm_bench.backend.log_file_writer.models import WriteOutcome


class RunLogWriterImpl:
    """Writes one ``RunLogEvent`` per call to a single run's dedicated log file."""

    def __init__(self, *, log_file: Path) -> None:
        self._log_file = log_file

    def write_event(self, event: RunLogEvent) -> WriteOutcome:
        """Append ``event``, rendered at the full Verbose field density, to the run log.

        Args:
            event: The pipeline event to record; not mutated.

        Returns:
            The typed outcome of the append (§8, §9); never raises for an I/O failure.
        """
        line = format_verbose_line(event)
        return append_line_safely(path=self._log_file, line=line)

    def close(self) -> None:
        """No-op: each write is self-contained via its own file descriptor.

        A run log is opened, appended to, and closed on every single call, so there is
        no open handle for this method to release.
        """
