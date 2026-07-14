"""Per-run cache of AdaptiveTimeoutService instances for the RUN_ANALYSIS bucket.

``make_adaptive_timeout_service`` produces an in-memory instance "bound to this run"
(``backend/adaptive_timeout/api.py``); nothing else in the codebase keeps one alive
across separate calls for a finished run. This cache is what lets a promoted
RUN_ANALYSIS last-known-good survive from one Generate/Regenerate click to the
next (RA-25) while staying fully independent of the pipeline's own per-run
instance used for the BENCHMARK_RUN activity's INFERENCE/JUDGE buckets (RA-22,
RA-24) — they are always separate objects.

Safe with no lock: the single-inference gate (``InferenceActivityStore``) guarantees
at most one ``RunAnalysisService.generate()`` call is in flight anywhere in the
application at any moment (a ``BENCHMARK_RUN`` and a ``JUDGE_ANALYSIS`` activity can
never overlap either), so this cache is never mutated concurrently.
"""

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry, RunId

__all__: list[str] = ["RunAdaptiveTimeoutCache"]


class RunAdaptiveTimeoutCache:
    """Lazily-populated ``run_id -> AdaptiveTimeoutService`` cache, process lifetime."""

    def __init__(self) -> None:
        self._by_run_id: dict[RunId, AdaptiveTimeoutService] = {}

    def get_or_create(
        self, *, run_id: RunId, snapshot: tuple[BenchmarkRunSettingEntry, ...]
    ) -> AdaptiveTimeoutService:
        """Return this run's RUN_ANALYSIS-bucket-capable service, creating it once.

        Args:
            run_id: The run being analyzed.
            snapshot: The run's own frozen settings snapshot (never live
                ``app_settings`` — §7's "read from the run snapshot" rule).

        Returns:
            The same ``AdaptiveTimeoutService`` instance for every call sharing
            this ``run_id``.
        """
        existing = self._by_run_id.get(run_id)
        if existing is not None:
            return existing
        created = make_adaptive_timeout_service(snapshot=snapshot)
        self._by_run_id[run_id] = created
        return created
