"""Public factory for the Log Formatting service (§2, §10)."""

import icontract

from ollama_llm_bench.backend.log_formatting._internal.service import LogFormatterImpl
from ollama_llm_bench.backend.log_formatting.protocols import LogFormatter

__all__: list[str] = ["make_log_formatter"]


@icontract.ensure(lambda result: result is not None)
def make_log_formatter() -> LogFormatter:
    """Construct the Log Formatting service.

    The service is pure and stateless — it takes no dependencies, performs no I/O, and
    the returned instance is safe to share across threads (formatting one event is a
    pure function of ``(event, verbosity)``, §10).

    Returns:
        A ``LogFormatter`` ready to format ``RunLogEvent`` values.
    """
    return LogFormatterImpl()
