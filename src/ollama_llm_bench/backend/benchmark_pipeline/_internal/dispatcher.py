"""The dispatcher-thread run loop: strictly serial, one unit in flight (D-R-16, DD-38)."""

from collections.abc import Callable

from ollama_llm_bench.backend.benchmark_pipeline._internal.grouping import (
    eligible_for_phase,
    group_by_provider_and_model,
    phase_applies,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import PHASE_ORDER, Phase
from ollama_llm_bench.backend.concurrency._internal.cancellation_token import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    ModelNameStr,
    ProviderIdStr,
    ResultPatch,
    RunId,
    RunMode,
)
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore

__all__: list[str] = [
    "run_all_phases",
    "run_phase",
]


def run_phase(  # noqa: PLR0913  # every keyword-only argument is a distinct collaborator
    # of the submit-await-persist-next loop (16_CONCURRENCY_MODEL.md §6.2); bundling them
    # into a struct would only indirect the read without reducing real coupling
    *,
    phase: Phase,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    runner: TaskRunner[ResultPatch],
    token: CancellationToken,
    results_store: ResultsStore,
    unit_factory: Callable[[BenchmarkResult], Callable[[], ResultPatch]],
) -> None:
    """Run one phase over its already-grouped eligible rows, strictly serially.

    Submits exactly one unit at a time, blocks on its Future, persists the
    result, then submits the next — never more than one unit in flight
    (16_CONCURRENCY_MODEL.md §6.2).

    Args:
        phase: The phase being run; used by callers to select `unit_factory`
            behaviour and carried here only for documentation/logging intent.
        groups: The phase's eligible rows, provider-then-model grouped, in
            first-seen order (never alphabetized).
        runner: The `TaskRunner` port a single unit is submitted to.
        token: The run's `CancellationToken`, checked before every unit.
        results_store: The single-writer store each unit's patch is persisted
            through before the next unit is submitted.
        unit_factory: Builds the blocking callable for one result row.

    Raises:
        TaskCancelledError: The token was cancelled at a safe checkpoint
            before a unit's submission.
    """
    del phase
    for _provider_id, _model_name, group_rows in groups:
        for result in group_rows:
            token.raise_if_cancelled()
            unit = unit_factory(result)
            patch = runner.submit(unit, token=token).result()
            results_store.update_result(result.result_id, patch)


def run_all_phases(  # noqa: PLR0913  # every keyword-only argument is a distinct
    # collaborator of the whole-run phase loop (08-B §3); bundling them into a struct
    # would only indirect the read without reducing real coupling
    *,
    run_mode: RunMode,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    run_id: RunId,
    runner: TaskRunner[ResultPatch],
    token: CancellationToken,
    results_store: ResultsStore,
    unit_factory_for_phase: Callable[[Phase, BenchmarkResult], Callable[[], ResultPatch]],
) -> None:
    """Drive every applicable phase to completion in strict order (08-B §3).

    Re-derives each phase's eligible set from freshly re-read persisted rows
    — a phase never begins until every eligible row of the prior phase left
    it, because eligibility itself is recomputed from what was just written.

    Args:
        run_mode: The run's fixed mode; only `GRADED` ever runs a grading phase.
        keyword_enabled: The run's resolved keyword-check toggle.
        cosine_enabled: The run's resolved cosine-check toggle.
        judge_enabled: The run's resolved judge-check toggle.
        run_id: The run whose rows are read fresh at the start of every phase.
        runner: The `TaskRunner` port each phase's units are submitted to.
        token: The run's `CancellationToken`, checked before every unit.
        results_store: The single-writer store rows are read from and
            written through.
        unit_factory_for_phase: Builds the blocking callable for one result
            row within a given phase.
    """
    for phase in PHASE_ORDER:
        if phase is Phase.INITIALIZATION:
            continue
        if not phase_applies(
            phase=phase,
            run_mode=run_mode,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
        ):
            continue
        current_rows = results_store.list_results(run_id)
        eligible = eligible_for_phase(current_rows, phase=phase)
        groups = group_by_provider_and_model(eligible)
        run_phase(
            phase=phase,
            groups=groups,
            runner=runner,
            token=token,
            results_store=results_store,
            unit_factory=_bind_phase(phase, unit_factory_for_phase),
        )


def _bind_phase(
    phase: Phase,
    unit_factory_for_phase: Callable[[Phase, BenchmarkResult], Callable[[], ResultPatch]],
) -> Callable[[BenchmarkResult], Callable[[], ResultPatch]]:
    """Partially apply `phase` onto a per-phase unit factory for `run_phase`'s single-arg contract."""

    def _for_result(result: BenchmarkResult) -> Callable[[], ResultPatch]:
        return unit_factory_for_phase(phase, result)

    return _for_result
