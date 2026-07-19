"""Shared confirmation / summary dialogs.

STORY-055 delivers the Run Summary dialog (``make_run_summary_dialog``);
STORY-056 adds the Rename Run dialog (``make_rename_run_dialog``); STORY-057
adds the Resume Summary dialog (``make_resume_summary_dialog``) and the Retry
Selection dialog (``make_retry_selection_dialog``). The other Common Dialogs
catalogued in the module inventory -- generate analysis -- are future stories'
responsibility and are deliberately not stubbed here.
"""

from ollama_llm_bench.ui.common_dialogs.api import (
    make_rename_run_dialog,
    make_resume_summary_dialog,
    make_retry_selection_dialog,
    make_run_summary_dialog,
)
from ollama_llm_bench.ui.common_dialogs.protocols import (
    RenameRunGateway,
    ResumeSummaryGateway,
    RetrySelectionGateway,
    RunSummaryGateway,
)

__all__: list[str] = [
    "RenameRunGateway",
    "ResumeSummaryGateway",
    "RetrySelectionGateway",
    "RunSummaryGateway",
    "make_rename_run_dialog",
    "make_resume_summary_dialog",
    "make_retry_selection_dialog",
    "make_run_summary_dialog",
]
