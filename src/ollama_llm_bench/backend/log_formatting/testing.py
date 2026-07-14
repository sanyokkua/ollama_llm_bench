"""A fake ``LogFormatter`` for downstream consumers' tests."""

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogVerbosity

__all__: list[str] = ["FakeLogFormatter"]


class FakeLogFormatter:
    """Records every ``format_event()`` call and returns a canned, settable fragment."""

    def __init__(self) -> None:
        self.calls: list[tuple[RunLogEvent, RunLogVerbosity]] = []
        self.next_fragment: str = '<span class="tone-info">EVENT</span>'

    def format_event(self, *, event: RunLogEvent, verbosity: RunLogVerbosity) -> str:
        """Record the call and return ``self.next_fragment`` (mutate it between calls)."""
        self.calls.append((event, verbosity))
        return self.next_fragment
