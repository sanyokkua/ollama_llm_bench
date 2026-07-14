"""Generate the single consolidated, mode-aware run-analysis narrative (§1).

Aggregates a finished run's data, calls a user-chosen ``(provider, model)`` analysis
model exactly once through its own ``RUN_ANALYSIS`` adaptive-timeout bucket, and
returns a ``RunAnalysisResult``. Never persists anything and never fails the run.
"""

from ollama_llm_bench.backend.run_analysis.api import make_run_analysis_service
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome, RunAnalysisResult
from ollama_llm_bench.backend.run_analysis.protocols import RunAnalysisService

__all__: list[str] = [
    "RunAnalysisOutcome",
    "RunAnalysisResult",
    "RunAnalysisService",
    "make_run_analysis_service",
]
