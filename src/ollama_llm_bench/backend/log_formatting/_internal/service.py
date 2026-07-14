"""The ``LogFormatter`` implementation — a pure, stateless, synchronous service (§10)."""

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting._internal.assembler import assemble

__all__: list[str] = ["LogFormatterImpl"]


class LogFormatterImpl:
    """Concrete ``LogFormatter`` — see the module docstring in ``_internal/assembler.py``
    for the full algorithm. Holds no state; safe to share across threads."""

    def format_event(self, *, event: RunLogEvent, verbosity: RunLogVerbosity) -> str:
        """See ``LogFormatter.format_event`` for the full contract."""
        return assemble(event, verbosity=verbosity)
