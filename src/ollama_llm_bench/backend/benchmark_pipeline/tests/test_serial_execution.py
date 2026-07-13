"""Proves: STORY-029-AC-2"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import run_phase
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.concurrency._internal.cancellation_token import CancellationToken
from ollama_llm_bench.backend.domain.models import ResultId, ResultPatch, ResultStatus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore


class _InlineTaskRunner:
    """Runs a unit synchronously on the calling thread — a test double only."""

    def submit(
        self, fn: Callable[[], ResultPatch], *, token: CancellationToken
    ) -> Future[ResultPatch]:
        future: Future[ResultPatch] = Future()
        future.set_result(fn())
        return future


def test_at_most_one_unit_in_flight_and_persist_before_next(fake_clock: Clock) -> None:
    """Proves: STORY-029-AC-2

    Each unit is submitted, awaited, and persisted before the next unit's
    callable is even constructed — proven by an execution-order log the
    fake ResultsStore and unit_factory both append to.
    """
    order: list[str] = []
    row_one = make_benchmark_result(result_id=1, status=ResultStatus.PENDING)
    row_two = make_benchmark_result(result_id=2, status=ResultStatus.PENDING)
    results_store = FakeResultsStore(initial=(row_one, row_two))
    token = CancellationToken(clock=fake_clock)

    def _unit_factory(result: object) -> Callable[[], ResultPatch]:
        result_id = result.result_id  # type: ignore[attr-defined]  # test double narrows below

        def _run() -> ResultPatch:
            order.append(f"run-{result_id}")
            return ResultPatch(status=ResultStatus.AWAITING_KEYWORD_CHECK)

        return _run

    original_update = results_store.update_result

    def _tracking_update(result_id: ResultId, patch: ResultPatch) -> None:
        order.append(f"persist-{result_id}")
        original_update(result_id, patch)

    results_store.update_result = _tracking_update  # type: ignore[method-assign]

    run_phase(
        phase=Phase.INFERENCE,
        groups=(("provider-1", "model-1", (row_one, row_two)),),
        runner=_InlineTaskRunner(),
        token=token,
        results_store=results_store,
        unit_factory=_unit_factory,
    )

    assert order == ["run-1", "persist-1", "run-2", "persist-2"]
