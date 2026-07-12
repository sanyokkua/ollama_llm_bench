"""Public factory for the Run Drift Detector (spec §6)."""

import icontract

from ollama_llm_bench.backend.run_drift._internal.detector import _RunDriftDetectorImpl
from ollama_llm_bench.backend.run_drift.protocols import RunDriftDetector

__all__: list[str] = ["make_run_drift_detector"]


@icontract.ensure(
    lambda result: result is not None,
    "factory must return a usable detector instance",
)
def make_run_drift_detector() -> RunDriftDetector:
    """Construct the stateless Run Drift Detector (spec §6).

    Returns:
        A pure, synchronous, idempotent RunDriftDetector with no constructor
        collaborators — every check operates only on the RunDriftDetectionInputs
        passed to detect().
    """
    return _RunDriftDetectorImpl()
