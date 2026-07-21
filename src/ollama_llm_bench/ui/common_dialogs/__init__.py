"""Shared confirmation / summary dialogs.

STORY-055 delivers the Run Summary dialog (``make_run_summary_dialog``);
STORY-056 adds the Rename Run dialog (``make_rename_run_dialog``); STORY-057
adds the Resume Summary dialog (``make_resume_summary_dialog``) and the Retry
Selection dialog (``make_retry_selection_dialog``); STORY-065 adds the Generate
Analysis dialog (``make_generate_analysis_dialog``).
"""

from ollama_llm_bench.ui.common_dialogs.api import (
    make_generate_analysis_dialog,
    make_rename_run_dialog,
    make_resume_summary_dialog,
    make_retry_selection_dialog,
    make_run_summary_dialog,
)
from ollama_llm_bench.ui.common_dialogs.models import GenerateAnalysisCollaborators
from ollama_llm_bench.ui.common_dialogs.protocols import (
    RenameRunGateway,
    ResumeSummaryGateway,
    RetrySelectionGateway,
    RunAnalysisDispatcher,
    RunSummaryGateway,
)

__all__: list[str] = [
    "GenerateAnalysisCollaborators",
    "RenameRunGateway",
    "ResumeSummaryGateway",
    "RetrySelectionGateway",
    "RunAnalysisDispatcher",
    "RunSummaryGateway",
    "make_generate_analysis_dialog",
    "make_rename_run_dialog",
    "make_resume_summary_dialog",
    "make_retry_selection_dialog",
    "make_run_summary_dialog",
]
