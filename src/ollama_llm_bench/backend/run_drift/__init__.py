"""Run Drift Detector — availability drift between a run snapshot and the live environment.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md``.

Compares a stopped/failed run's frozen configuration snapshot — its providers,
models, and settings, captured at run creation — against the application's
current live configuration at the moment the user asks to resume that run, and
produces an ordered, possibly empty ``tuple[DriftWarning, ...]`` describing every
availability difference that could affect the resumed run: a provider removed,
disabled, or unreachable; its frozen API-key environment variable no longer
resolving; a frozen test/judge/embedding model no longer served.

The detector is strictly read-only, synchronous, pure, and idempotent — it never
modifies the run, the snapshot, the catalogs, or live settings, and it never
decides whether a resume proceeds; it only reports environment-satisfiability
drift (DD-57), never mere settings differences.
"""

from ollama_llm_bench.backend.run_drift.api import make_run_drift_detector
from ollama_llm_bench.backend.run_drift.models import (
    DriftKind,
    DriftSeverity,
    DriftWarning,
    RunDriftDetectionInputs,
)
from ollama_llm_bench.backend.run_drift.protocols import RunDriftDetector

__all__: list[str] = [
    "DriftKind",
    "DriftSeverity",
    "DriftWarning",
    "RunDriftDetectionInputs",
    "RunDriftDetector",
    "make_run_drift_detector",
]
