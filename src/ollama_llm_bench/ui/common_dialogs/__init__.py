"""Shared confirmation / summary dialogs.

STORY-055 delivers the Run Summary dialog (``make_run_summary_dialog``);
STORY-056 adds the Rename Run dialog (``make_rename_run_dialog``). The other
Common Dialogs catalogued in the module inventory -- resume summary, retry
selection, generate analysis -- are future stories' responsibility and are
deliberately not stubbed here.
"""

from ollama_llm_bench.ui.common_dialogs.api import make_rename_run_dialog, make_run_summary_dialog
from ollama_llm_bench.ui.common_dialogs.protocols import RenameRunGateway, RunSummaryGateway

__all__: list[str] = [
    "RenameRunGateway",
    "RunSummaryGateway",
    "make_rename_run_dialog",
    "make_run_summary_dialog",
]
