"""Benchmark workspace right panel: the Result widget shell (STORY-061) -- the
run-selector header, the four-tab strip, and the uniform export footer. The four
tab bodies (Summary, Details, Charts, Run Analysis) mount into this shell's empty
tab-body host containers in STORY-062..065.
"""

from ollama_llm_bench.ui.results.api import make_result_widget
from ollama_llm_bench.ui.results.models import (
    FooterViewModel,
    ResultCollaborators,
    ResultViewModel,
)
from ollama_llm_bench.ui.results.protocols import ExportFilenameHelper, ResultGateway

__all__: list[str] = [
    "ExportFilenameHelper",
    "FooterViewModel",
    "ResultCollaborators",
    "ResultGateway",
    "ResultViewModel",
    "make_result_widget",
]
