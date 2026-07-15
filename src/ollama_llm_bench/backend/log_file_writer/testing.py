"""Fakes of ``AppLogWriter``/``RunLogWriter`` for downstream consumers' tests."""

from ollama_llm_bench.backend.domain import RunLogEvent
from ollama_llm_bench.backend.log_file_writer.models import WriteOutcome

__all__: list[str] = [
    "FakeAppLogWriter",
    "FakeRunLogWriter",
]


class FakeAppLogWriter:
    """Records every ``write_line()`` call and returns a canned, settable outcome."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.next_outcome: WriteOutcome = WriteOutcome(succeeded=True)
        self.closed: bool = False

    def write_line(self, text: str) -> WriteOutcome:
        """Record the call and return ``self.next_outcome`` (mutate it between calls)."""
        self.calls.append(text)
        return self.next_outcome

    def close(self) -> None:
        """Record that the writer was closed."""
        self.closed = True


class FakeRunLogWriter:
    """Records every ``write_event()`` call and returns a canned, settable outcome."""

    def __init__(self) -> None:
        self.calls: list[RunLogEvent] = []
        self.next_outcome: WriteOutcome = WriteOutcome(succeeded=True)
        self.closed: bool = False

    def write_event(self, event: RunLogEvent) -> WriteOutcome:
        """Record the call and return ``self.next_outcome`` (mutate it between calls)."""
        self.calls.append(event)
        return self.next_outcome

    def close(self) -> None:
        """Record that the writer was closed."""
        self.closed = True
