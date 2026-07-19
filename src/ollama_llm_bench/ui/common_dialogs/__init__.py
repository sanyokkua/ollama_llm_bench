"""Shared confirmation / summary dialogs.

STORY-055 delivers exactly the Run Summary dialog (``make_run_summary_dialog``).
The other Common Dialogs catalogued in the module inventory -- resume summary,
retry selection, rename run, generate analysis -- are future stories'
responsibility and are deliberately not stubbed here.
"""

from ollama_llm_bench.ui.common_dialogs.api import make_run_summary_dialog
from ollama_llm_bench.ui.common_dialogs.protocols import RunSummaryGateway

__all__: list[str] = ["RunSummaryGateway", "make_run_summary_dialog"]
