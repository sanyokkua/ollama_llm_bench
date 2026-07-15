"""Rotating application-log writer + per-run event-log writer + run-log cleanup.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §4, §8,
§9 and ``docs/v3_specification/11_Services_and_Algorithms/15_LOG_FORMATTING.md`` §7. This
module writes the rotating ``<app-data>/logs/app/app.log`` sink and one
``<app-data>/logs/run/run_<run_id>_<unix_ts>.log`` file per benchmark run, always at the
full Verbose field density regardless of the on-screen ``ui.run_log_verbosity``, plus
the startup count-based cleanup that prunes run logs to a fixed retention count.
"""

from ollama_llm_bench.backend.log_file_writer.api import (
    cleanup_run_logs,
    make_app_log_writer,
    make_run_log_writer,
)
from ollama_llm_bench.backend.log_file_writer.models import WriteFailureReason, WriteOutcome
from ollama_llm_bench.backend.log_file_writer.protocols import AppLogWriter, RunLogWriter

__all__: list[str] = [
    "AppLogWriter",
    "RunLogWriter",
    "WriteFailureReason",
    "WriteOutcome",
    "cleanup_run_logs",
    "make_app_log_writer",
    "make_run_log_writer",
]
