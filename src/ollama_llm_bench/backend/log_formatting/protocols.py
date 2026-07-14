"""The ``LogFormatter`` contract (`01_MODULE_INVENTORY.md` §4.5)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogVerbosity

__all__: list[str] = ["LogFormatter"]


class LogFormatter(Protocol):
    """Render one ``RunLogEvent`` into a verbosity-selected, one-line HTML fragment."""

    def format_event(self, *, event: RunLogEvent, verbosity: RunLogVerbosity) -> str:
        """Fast-synchronous; safe to call from any thread, including the GUI thread.

        Performs no I/O and never raises — a malformed ``event`` or an unrecognized
        ``verbosity``/kind still produces a renderable line (§9). The caller invokes
        this once per event; there is no batch/list variant — the Progress widget's
        re-render on a verbosity change (§6.5) calls this once per cached event.

        Args:
            event: The pipeline event to render; not mutated.
            verbosity: The field density to select (§6.2); an unrecognized value is
                treated as ``NORMAL``.

        Returns:
            A single-line HTML fragment with balanced tags and no newline.
        """
        ...
