"""Benchmark workspace centre panel.

The live view of one benchmark run: header (stage badge, run name, rename pencil,
Pause/Resume, Stop), run-progress counters, the segmented stage progress bar, and the
model/provider stability callouts (STORY-058). The Current-Task section and the Run
Event-Log panel are added by STORY-059 and STORY-060.
"""

from ollama_llm_bench.ui.progress.api import make_progress_widget
from ollama_llm_bench.ui.progress.models import (
    CountersViewModel,
    HeaderAffordances,
    ProgressViewModel,
    RunStage,
    StabilityViewModel,
)
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = [
    "CountersViewModel",
    "HeaderAffordances",
    "ProgressGateway",
    "ProgressViewModel",
    "RunStage",
    "StabilityViewModel",
    "make_progress_widget",
]
