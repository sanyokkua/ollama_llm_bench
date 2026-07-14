"""Event -> display-string formatter.

Turns one ``RunLogEvent`` into a single-line HTML fragment carrying exactly the fields
the current ``RunLogVerbosity`` selects, tone-classed by event kind, HTML-escaped, and
truncated at Normal verbosity (`11_Services_and_Algorithms/15_LOG_FORMATTING.md`).
"""

from ollama_llm_bench.backend.log_formatting.api import make_log_formatter
from ollama_llm_bench.backend.log_formatting.protocols import LogFormatter

__all__: list[str] = ["LogFormatter", "make_log_formatter"]
