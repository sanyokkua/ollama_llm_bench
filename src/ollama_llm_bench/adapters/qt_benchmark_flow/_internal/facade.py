"""``QtBenchmarkFlow`` — the thin Qt-side facade over the backend benchmark pipeline.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§11 (the ``BenchmarkFlowApi`` method surface, the fast-synchronous-on-GUI-thread
contract, the idle no-op rules, the never-raises guarantee, and the bounded ``shutdown``
semantics this facade forwards unchanged).

``QtBenchmarkFlow`` carries no business logic of its own: every method is a single-line
forward to the identically-named method on the backend ``BenchmarkFlowApi`` it holds. The
pipeline itself already owns the dispatcher-thread hand-off (``RunDispatcher``, DD-38) via
its own constructor injection — the composition root wires that dispatcher into
``make_benchmark_pipeline`` directly, before this facade is ever constructed, so this class
does not hold a `RunDispatcher` or `TaskRunner` reference of its own.
"""

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.domain.models import BenchmarkRun, RunId, RunStartRequest

__all__: list[str] = [
    "QtBenchmarkFlow",
]


class QtBenchmarkFlow:
    """Forwards every ``BenchmarkFlowApi`` control/query call to the backend pipeline.

    Structurally implements the same call surface as ``BenchmarkFlowApi`` so
    the UI layer can depend on this facade without importing the backend
    pipeline module directly (``01_MODULE_INVENTORY.md`` §5).
    """

    def __init__(self, *, pipeline: BenchmarkFlowApi) -> None:
        """Store the backend pipeline this facade forwards every call to.

        Args:
            pipeline: The backend ``BenchmarkFlowApi`` implementation, already
                wired with its own ``RunDispatcher`` by the composition root.
        """
        self._pipeline = pipeline

    def start(self, request: RunStartRequest) -> RunId:
        """Forward to ``BenchmarkFlowApi.start`` and return its result unchanged."""
        return self._pipeline.start(request)

    def resume(self, run_id: RunId) -> None:
        """Forward to ``BenchmarkFlowApi.resume``."""
        self._pipeline.resume(run_id)

    def pause(self) -> None:
        """Forward to ``BenchmarkFlowApi.pause``."""
        self._pipeline.pause()

    def resume_paused(self) -> None:
        """Forward to ``BenchmarkFlowApi.resume_paused``."""
        self._pipeline.resume_paused()

    def stop(self) -> None:
        """Forward to ``BenchmarkFlowApi.stop``."""
        self._pipeline.stop()

    def shutdown(self, timeout_ms: int) -> None:
        """Forward to ``BenchmarkFlowApi.shutdown``."""
        self._pipeline.shutdown(timeout_ms)

    def is_running(self) -> bool:
        """Forward to ``BenchmarkFlowApi.is_running`` and return its result unchanged."""
        return self._pipeline.is_running()

    def current_run(self) -> BenchmarkRun | None:
        """Forward to ``BenchmarkFlowApi.current_run`` and return its result unchanged."""
        return self._pipeline.current_run()
