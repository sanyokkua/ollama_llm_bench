"""Proves: STORY-029-AC-1"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import run_all_phases
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.concurrency._internal.cancellation_token import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunMode,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore

# Maps a phase to the ResultPatch status a unit in that phase produces, simulating
# a run where every row passes and every grading phase (keyword, cosine) is enabled.
_NEXT_STATUS_BY_PHASE: dict[Phase, ResultStatus] = {
    Phase.INFERENCE: ResultStatus.AWAITING_KEYWORD_CHECK,
    Phase.KEYWORD_CHECK: ResultStatus.AWAITING_COSINE_CHECK,
    Phase.COSINE_CHECK: ResultStatus.COMPLETED,
}


class _InlineTaskRunner:
    """Runs a unit synchronously on the calling thread — a test double only.

    Typed `object` (not `ResultPatch`) to structurally satisfy `TaskRunner[object]`,
    the same convention `backend/readiness` and this package's shared
    `conftest.py` double already use — `run_all_phases` accepts `TaskRunner[object]`.
    """

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> Future[object]:
        future: Future[object] = Future()
        future.set_result(fn())
        return future


def _unit_factory_for_phase(phase: Phase, result: BenchmarkResult) -> Callable[[], ResultPatch]:
    """Build a stub unit that advances `result` to the next phase's status."""

    def _run() -> ResultPatch:
        return ResultPatch(status=_NEXT_STATUS_BY_PHASE[phase])

    return _run


def test_no_row_enters_a_later_phase_before_the_earlier_phase_fully_drains(
    fake_clock: Clock,
) -> None:
    """Proves: STORY-029-AC-1

    Over a mixed-status seed spanning two phases (some rows PENDING, some
    already AWAITING_KEYWORD_CHECK), no row reaches AWAITING_COSINE_CHECK
    before every row that started PENDING reached AWAITING_KEYWORD_CHECK —
    proven by the persisted update order, since `run_all_phases` re-derives
    each phase's eligible set only after the prior phase's `run_phase` loop
    returns.
    """
    pending_one = make_benchmark_result(result_id=1, status=ResultStatus.PENDING)
    pending_two = make_benchmark_result(result_id=2, status=ResultStatus.PENDING)
    already_awaiting_keyword = make_benchmark_result(
        result_id=3, status=ResultStatus.AWAITING_KEYWORD_CHECK
    )
    results_store = FakeResultsStore(initial=(pending_one, pending_two, already_awaiting_keyword))
    token = CancellationToken(clock=fake_clock)

    order: list[tuple[ResultId, ResultStatus | None]] = []
    original_update = results_store.update_result

    def _tracking_update(result_id: ResultId, patch: ResultPatch) -> None:
        order.append((result_id, patch.status))
        original_update(result_id, patch)

    results_store.update_result = _tracking_update  # type: ignore[method-assign]

    run_all_phases(
        run_mode=RunMode.GRADED,
        keyword_enabled=True,
        cosine_enabled=True,
        judge_enabled=False,
        run_id=1,
        runner=_InlineTaskRunner(),
        token=token,
        results_store=results_store,
        unit_factory_for_phase=_unit_factory_for_phase,
    )

    keyword_check_index = max(
        index
        for index, (_result_id, status) in enumerate(order)
        if status is ResultStatus.AWAITING_KEYWORD_CHECK
    )
    first_cosine_check_index = min(
        index
        for index, (_result_id, status) in enumerate(order)
        if status is ResultStatus.AWAITING_COSINE_CHECK
    )

    assert keyword_check_index < first_cosine_check_index
