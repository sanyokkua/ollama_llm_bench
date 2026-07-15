"""The ``AppLogWriter`` and ``RunLogWriter`` contracts (`01_MODULE_INVENTORY.md` §4.5)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import RunLogEvent
from ollama_llm_bench.backend.log_file_writer.models import WriteOutcome

__all__: list[str] = [
    "AppLogWriter",
    "RunLogWriter",
]


class AppLogWriter(Protocol):
    """Writes one line at a time to the rotating application log (§4.1, §8.1)."""

    def write_line(self, text: str) -> WriteOutcome:
        """Append ``text`` as one line, rotating first if this write would exceed the
        configured size trigger.

        Blocking file I/O; call from a worker thread, never the GUI thread.

        Args:
            text: The already-formatted application-log record.

        Returns:
            The typed outcome of the append/rotation; never raises for an I/O failure.
        """
        ...

    def close(self) -> None:
        """Release any resource this writer holds open."""
        ...


class RunLogWriter(Protocol):
    """Writes one ``RunLogEvent`` at a time to a single run's dedicated log file (§4.2)."""

    def write_event(self, event: RunLogEvent) -> WriteOutcome:
        """Append ``event``, rendered at the full Verbose field density.

        Blocking file I/O; call from a worker thread, never the GUI thread.

        Args:
            event: The pipeline event to record; not mutated.

        Returns:
            The typed outcome of the append; never raises for an I/O failure.
        """
        ...

    def close(self) -> None:
        """Release any resource this writer holds open."""
        ...
