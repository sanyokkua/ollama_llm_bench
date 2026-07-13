"""The concrete `BenchmarkFlowApi` lifecycle controller (08-E §11).

Wires gate admission (SPEC-036/DD-50), run/result-row creation, the dispatcher
thread (DD-38), the five-phase batched loop (Tasks 1-8 of this story), the
run-start embedding probe (DD-48), and the DD-42 halt-outcome resolution into
one never-raising `BenchmarkFlowApi` implementation.
"""

from collections.abc import Callable
from dataclasses import dataclass
import threading

import msgspec

from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import run_all_phases
from ollama_llm_bench.backend.benchmark_pipeline._internal.embedding_probe import (
    run_embedding_probe,
    run_needs_embeddings,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.events import (
    emit_run_failed,
    emit_run_finished,
    emit_run_paused,
    emit_run_resumed,
    emit_run_start_failed,
    emit_run_started,
    emit_run_stopped,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.outcome import resolve_halt_outcome
from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    build_cosine_unit,
    build_inference_unit,
    build_judge_unit,
    build_keyword_unit,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.protocols import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import CancellationToken, make_cancellation_token
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunProviderEntry,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    CancelReason,
    ErrorKind,
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    ModelRole,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
    RunStatusPatch,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.errors import AppError, ContractViolationError, TaskCancelledError
from ollama_llm_bench.backend.evaluation import (
    make_cosine_evaluator,
    make_judge_evaluator,
    make_keyword_evaluator,
    make_sanity_checker,
)
from ollama_llm_bench.backend.evaluation.protocols import (
    CosineEvaluator,
    JudgeEvaluator,
    KeywordEvaluator,
    SanityChecker,
)
from ollama_llm_bench.backend.events.models import (
    RunFailedEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStartFailedEvent,
    RunStoppedEvent,
)
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = ["_BenchmarkFlowApiImpl"]

_NON_TERMINAL_STATUSES: frozenset[ResultStatus] = frozenset(
    {
        ResultStatus.PENDING,
        ResultStatus.RUNNING_INFERENCE,
        ResultStatus.AWAITING_KEYWORD_CHECK,
        ResultStatus.AWAITING_COSINE_CHECK,
        ResultStatus.AWAITING_JUDGE_CHECK,
    }
)
"""Statuses a row can still leave; mirrors `FakeResultsStore`'s `_IN_FLIGHT_STATUSES`
plus `PENDING` — used only to compute `completed_tasks` at settle time."""

_DISPATCHER_THREAD_NAME = "pipeline-dispatcher"


@dataclass(slots=True, frozen=True)
class _PhaseToggles:
    """This run's four resolved `eval.*` grading toggles (`_internal`-only, never
    crosses this module's boundary — see `coding-style.md`'s dataclass exception)."""

    keyword_enabled: bool
    cosine_enabled: bool
    judge_enabled: bool
    force_judge: bool


@dataclass(slots=True, frozen=True)
class _RunEvaluators:
    """This run's four constructed evaluation-phase evaluators (`_internal`-only)."""

    sanity_checker: SanityChecker
    keyword_evaluator: KeywordEvaluator
    cosine_evaluator: CosineEvaluator
    judge_evaluator: JudgeEvaluator | None


def _build_initial_results(
    *, run: BenchmarkRun, tasks: tuple[BenchmarkTask, ...]
) -> tuple[BenchmarkResult, ...]:
    """Build the initial `PENDING` result rows: the TEST-role x task cross product.

    Args:
        run: The freshly created run, already carrying its real `run_id`.
        tasks: The run's frozen tasks, as currently staged in `TasksStore`.

    Returns:
        One `BenchmarkResult` per `(test model, task)` pair, `result_id`
        assigned by a simple per-call counter (see the module docstring
        concern recorded in this story's report: `ResultsStore.create_results`
        states no id-assignment contract, so the real persistence
        implementation is expected to own final id assignment).
    """
    provider_names = {entry.provider_id: entry.name for entry in run.providers}
    test_models = tuple(m for m in run.models if m.role is ModelRole.TEST)
    rows: list[BenchmarkResult] = []
    next_id: ResultId = 1
    for model_entry in test_models:
        for task in tasks:
            rows.append(
                BenchmarkResult(
                    result_id=next_id,
                    run_id=run.run_id,
                    task_id=task.task_id,
                    provider_id=model_entry.provider_id,
                    provider_name=provider_names.get(
                        model_entry.provider_id, model_entry.provider_id
                    ),
                    model_name=model_entry.model_name,
                    status=ResultStatus.PENDING,
                    created_at=run.created_at,
                )
            )
            next_id += 1
    return tuple(rows)


class _BenchmarkFlowApiImpl:
    """Concrete `BenchmarkFlowApi`: gate admission, dispatch, and halt handling.

    Owns a small locked state surface (`_is_running`, `_current_run`,
    `_token`, `_dispatcher_thread`) read from the GUI thread while the
    dispatcher thread runs the five-phase loop. Never raises to its caller
    (DD-44) — every dependency failure becomes result-row or run-header data.
    """

    def __init__(  # noqa: PLR0913  # every keyword-only argument is a distinct,
        # already-Protocol-typed collaborator this lifecycle controller wires
        # together (project-structure.md's "one implementation with constructor
        # configuration" module shape) — bundling them into a struct would only
        # indirect the read without reducing real coupling
        self,
        *,
        results_store: ResultsStore,
        runs_store: RunsStore,
        tasks_store: TasksStore,
        inference_activity_store: InferenceActivityStore,
        task_runner: TaskRunner[ResultPatch],
        bus: EventBus,
        clock: Clock,
        embedding_service: EmbeddingService,
        provider_registry: ProviderRegistry,
        settings_service: SettingsService,
        run_snapshot_builder: RunSnapshotBuilder,
    ) -> None:
        self._results_store = results_store
        self._runs_store = runs_store
        self._tasks_store = tasks_store
        self._inference_activity_store = inference_activity_store
        self._task_runner = task_runner
        self._bus = bus
        self._clock = clock
        self._embedding_service = embedding_service
        self._provider_registry = provider_registry
        self._settings_service = settings_service
        self._run_snapshot_builder = run_snapshot_builder
        self._lock = threading.Lock()
        self._is_running = False
        self._current_run: BenchmarkRun | None = None
        self._token: CancellationToken | None = None
        self._dispatcher_thread: threading.Thread | None = None

    def start(self, request: RunStartRequest) -> RunId:
        """Admit under the gate, create the run, and dispatch it (see class docstring)."""
        context = InferenceActivityContext(
            activity=InferenceActivity.BENCHMARK_RUN, started_at=self._clock.monotonic_ms()
        )
        lease = self._inference_activity_store.try_acquire(InferenceActivity.BENCHMARK_RUN, context)
        if lease is None:
            emit_run_start_failed(
                self._bus,
                RunStartFailedEvent(
                    run_mode=request.run_mode,
                    error_kind=ErrorKind.OTHER,
                    error_message="another inference activity already holds the single-inference gate",
                    attempted_at=self._clock.now_utc(),
                ),
            )
            no_run_created_sentinel: RunId = 0
            return no_run_created_sentinel
        run = self._prepare_and_persist_run(request)
        token = make_cancellation_token(clock=self._clock)
        with self._lock:
            self._token = token
            self._current_run = run
            self._is_running = True
        thread = threading.Thread(
            target=self._dispatch_run,
            name=_DISPATCHER_THREAD_NAME,
            kwargs={"run": run, "lease": lease, "token": token},
            daemon=False,
        )
        with self._lock:
            self._dispatcher_thread = thread
        thread.start()
        self._emit_run_started(run)
        return run.run_id

    def _prepare_and_persist_run(self, request: RunStartRequest) -> BenchmarkRun:
        """Build the run header, persist it and its initial result rows.

        SCOPE BOUNDARY (STORY-029 Task 9): `TasksStore` is assumed to already
        carry this run's frozen task rows, staged by a future New-Benchmark
        use case that does not exist yet (`backend/task_files` and
        `backend/performance_task_generator` are both unimplemented, zero-LOC
        stubs as of this story). In real production use today this list is
        empty; tests seed `TasksStore` directly. This is a deliberate, narrow
        scope boundary agreed with the project owner, not a bug.
        """
        run = self._build_run(request)
        run_id = self._runs_store.create_run(run)
        run = msgspec.structs.replace(run, run_id=run_id)
        tasks = self._tasks_store.list_tasks(run_id)
        initial_results = _build_initial_results(run=run, tasks=tasks)
        self._results_store.create_results(initial_results)
        # NOTE (concern flagged in this story's report): RunStatusPatch has no
        # total_tasks field, so total_tasks cannot be corrected post-insert
        # here even though it is only known after list_tasks(run_id) returns.
        # started_at is persisted below; total_tasks stays at the
        # construction-time value (0) until a later story extends
        # RunStatusPatch/RunsStore.
        self._runs_store.update_run_status(
            run_id, RunStatusPatch(total_elapsed_ms=0, started_at=run.created_at)
        )
        return run

    def _build_run(self, request: RunStartRequest) -> BenchmarkRun:
        """Assemble the pre-insert `BenchmarkRun` header (run_id is a placeholder)."""
        settings_snapshot = self._resolve_settings_snapshot(request)
        models = self._resolve_model_entries(request)
        providers = self._resolve_provider_entries(models)
        judge_provider_id, judge_provider_name = self._resolve_judge_provider(request, providers)
        embedding_provider_name, embedding_model_name = self._resolve_embedding_target(
            request, providers
        )
        now = self._clock.now_utc()
        placeholder_run_id: RunId = 0
        return BenchmarkRun(
            run_id=placeholder_run_id,
            run_name=None,
            timestamp=now,
            run_mode=request.run_mode,
            status=RunStatus.INCOMPLETE,
            total_tasks=0,
            completed_tasks=0,
            total_elapsed_ms=0,
            judge_provider_id=judge_provider_id,
            judge_provider_name=judge_provider_name,
            embedding_provider_name=embedding_provider_name,
            embedding_model_name=embedding_model_name,
            schema_version=1,
            created_at=now,
            started_at=None,
            finished_at=None,
            models=models,
            providers=providers,
            settings_snapshot=settings_snapshot,
        )

    def _resolve_settings_snapshot(
        self, request: RunStartRequest
    ) -> tuple[BenchmarkRunSettingEntry, ...]:
        """Overlay `request.setting_overrides` onto the frozen base snapshot."""
        base = {
            entry.setting_key: entry.setting_value
            for entry in self._run_snapshot_builder.build_snapshot()
        }
        base.update({entry.setting_key: entry.setting_value for entry in request.setting_overrides})
        return tuple(
            BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
            for key, value in base.items()
        )

    def _resolve_model_entries(
        self, request: RunStartRequest
    ) -> tuple[BenchmarkRunModelEntry, ...]:
        """Build the run's frozen model roster: TEST models, then JUDGE, then EMBEDDING."""
        entries = [
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=m.provider_id, model_name=m.model_name
            )
            for m in request.test_models
        ]
        if request.judge_model is not None:
            entries.append(
                BenchmarkRunModelEntry(
                    role=ModelRole.JUDGE,
                    provider_id=request.judge_model.provider_id,
                    model_name=request.judge_model.model_name,
                )
            )
        if request.embedding_model is not None:
            entries.append(
                BenchmarkRunModelEntry(
                    role=ModelRole.EMBEDDING,
                    provider_id=request.embedding_model.provider_id,
                    model_name=request.embedding_model.model_name,
                )
            )
        return tuple(entries)

    def _resolve_provider_entries(
        self, models: tuple[BenchmarkRunModelEntry, ...]
    ) -> tuple[BenchmarkRunProviderEntry, ...]:
        """Snapshot every enabled provider referenced by `models`."""
        wanted_ids = {m.provider_id for m in models}
        enabled = self._provider_registry.list_enabled()
        return tuple(
            BenchmarkRunProviderEntry(
                provider_id=config.provider_id,
                name=config.name,
                provider_type=config.provider_type,
                base_url=config.base_url,
                api_key_raw=config.api_key_raw,
                azure_endpoint_raw=config.azure_endpoint_raw,
                azure_deployment_raw=config.azure_deployment_raw,
                azure_api_version_raw=config.azure_api_version_raw,
            )
            for config in enabled
            if config.provider_id in wanted_ids
        )

    def _resolve_judge_provider(
        self, request: RunStartRequest, providers: tuple[BenchmarkRunProviderEntry, ...]
    ) -> tuple[str | None, str | None]:
        """Resolve `(judge_provider_id, judge_provider_name)`, `None` when no judge model."""
        if request.judge_model is None:
            return None, None
        provider_id = request.judge_model.provider_id
        name = next((p.name for p in providers if p.provider_id == provider_id), None)
        return provider_id, name

    def _resolve_embedding_target(
        self, request: RunStartRequest, providers: tuple[BenchmarkRunProviderEntry, ...]
    ) -> tuple[str | None, str | None]:
        """Resolve `(embedding_provider_name, embedding_model_name)`, `None` when unset."""
        if request.embedding_model is None:
            return None, None
        provider_id = request.embedding_model.provider_id
        name = next((p.name for p in providers if p.provider_id == provider_id), None)
        return name, request.embedding_model.model_name

    def _emit_run_started(self, run: BenchmarkRun) -> None:
        """Emit `_run_started` after the dispatcher thread has already been launched."""
        test_targets = tuple(
            (m.provider_id, m.model_name) for m in run.models if m.role is ModelRole.TEST
        )
        judge_entry = next((m for m in run.models if m.role is ModelRole.JUDGE), None)
        embedding_entry = next((m for m in run.models if m.role is ModelRole.EMBEDDING), None)
        emit_run_started(
            self._bus,
            RunStartedEvent(
                run_id=run.run_id,
                run_name=run.run_name or "",
                run_mode=run.run_mode,
                started_at=run.created_at,
                total_tasks=run.total_tasks,
                test_targets=test_targets,
                judge_target=(
                    (judge_entry.provider_id, judge_entry.model_name)
                    if judge_entry is not None
                    else None
                ),
                embedding_target=(
                    (embedding_entry.provider_id, embedding_entry.model_name)
                    if embedding_entry is not None
                    else None
                ),
            ),
        )

    def _emit_run_resumed(
        self, run: BenchmarkRun, *, current_rows: tuple[BenchmarkResult, ...]
    ) -> None:
        """Emit `_run_resumed` after the dispatcher thread has already been launched."""
        completed_count = sum(1 for row in current_rows if row.status not in _NON_TERMINAL_STATUSES)
        emit_run_resumed(
            self._bus,
            RunResumedEvent(
                run_id=run.run_id,
                resumed_at=self._clock.now_utc(),
                completed_tasks=completed_count,
                total_tasks=run.total_tasks,
            ),
        )

    def resume(self, run_id: RunId) -> None:
        """Resume a `STOPPED`/`FAILED` run's unfinished rows (STORY-029-AC-6).

        Admits under the single-inference gate first, exactly like `start`
        (SPEC-036, DD-50); a held gate makes this call a silent no-op. Any
        row still `RUNNING_INFERENCE` (an artefact of a crash mid-unit, since
        `list_resumable_results` itself only selects `PENDING` and retryable
        failure rows) is reset to `PENDING` before dispatch. The run's
        already-persisted `settings_snapshot`/model/provider entries are
        reused verbatim — this method never re-resolves live settings.
        """
        context = InferenceActivityContext(
            activity=InferenceActivity.BENCHMARK_RUN, started_at=self._clock.monotonic_ms()
        )
        lease = self._inference_activity_store.try_acquire(InferenceActivity.BENCHMARK_RUN, context)
        if lease is None:
            return
        run = self._runs_store.get_run(run_id)
        # `list_resumable_results` selects PENDING + retryable-failure rows
        # (its own docstring) — this call confirms that set per AC-6; the
        # actual re-run selection is `run_all_phases`' own per-phase
        # eligibility filter over `list_results`, which is why the return
        # value itself is not threaded further here.
        self._results_store.list_resumable_results(run_id)
        current_rows = self._results_store.list_results(run_id)
        stuck_ids = tuple(
            row.result_id for row in current_rows if row.status is ResultStatus.RUNNING_INFERENCE
        )
        if stuck_ids:
            self._results_store.reset_results(stuck_ids)
        token = make_cancellation_token(clock=self._clock)
        with self._lock:
            self._token = token
            self._current_run = run
            self._is_running = True
        thread = threading.Thread(
            target=self._dispatch_run,
            name=_DISPATCHER_THREAD_NAME,
            kwargs={"run": run, "lease": lease, "token": token},
            daemon=False,
        )
        with self._lock:
            self._dispatcher_thread = thread
        thread.start()
        self._emit_run_resumed(run, current_rows=current_rows)

    def pause(self) -> None:
        """Request a cooperative soft cancel on the run's live token, if any."""
        with self._lock:
            token = self._token
        if token is not None:
            token.cancel(reason=CancelReason.USER_PAUSE, hard=False)

    def resume_paused(self) -> None:
        """Deliberately a no-op for now — see this story's report for scope reasoning.

        `is_running()` already covers the "idle or not paused" no-op case the
        Protocol documents. The "currently parked paused" case would require
        constructing a new `CancellationToken` and a new dispatcher thread —
        exactly Task 10's resume-from-pause responsibility. Half-implementing
        that here risks a subtly wrong flow Task 10 would then have to detect
        and undo, so this method stays a no-op in both cases until Task 10
        lands.
        """
        return

    def stop(self) -> None:
        """Request a hard cancel (`USER_STOP`) on the run's live token, if any."""
        with self._lock:
            token = self._token
        if token is not None:
            token.cancel(reason=CancelReason.USER_STOP, hard=True)

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on quit; wait up to timeout_ms then return.

        Requests a hard stop (idle when no run is active) and joins the
        dispatcher thread up to `timeout_ms`. `Thread.join` returns silently
        on timeout without raising — a still-alive thread after the bound
        elapses is surfaced only via `is_running()` still reporting `True`,
        never as an exception (DD-44).
        """
        self.stop()
        with self._lock:
            thread = self._dispatcher_thread
        if thread is not None:
            thread.join(timeout=timeout_ms / 1000)

    def is_running(self) -> bool:
        """Whether a run is currently executing (including the paused state)."""
        with self._lock:
            return self._is_running

    def current_run(self) -> BenchmarkRun | None:
        """The run currently being executed, or `None` once it has settled."""
        with self._lock:
            return self._current_run if self._is_running else None

    def _dispatch_run(
        self, *, run: BenchmarkRun, lease: GateLease, token: CancellationToken
    ) -> None:
        """Run on the `pipeline-dispatcher` thread; never the GUI thread."""
        dispatch_start_ms = self._clock.monotonic_ms()
        already_settled = False
        try:
            already_settled = self._run_phases(
                run=run, token=token, lease=lease, dispatch_start_ms=dispatch_start_ms
            )
        except TaskCancelledError:
            pass  # the halt path below reads the token snapshot regardless of exit reason
        finally:
            if not already_settled:
                self._settle_run(
                    run=run, token=token, lease=lease, dispatch_start_ms=dispatch_start_ms
                )

    def _run_phases(
        self,
        *,
        run: BenchmarkRun,
        token: CancellationToken,
        lease: GateLease,
        dispatch_start_ms: int,
    ) -> bool:
        """Construct this run's evaluators and drive the five-phase loop.

        Returns:
            `True` when this call already brought the run to a terminal,
            persisted state itself (a construction-time `AppError` while
            building evaluators, or a failed embedding probe) — the caller
            must NOT call `_settle_run` again for that path (this method
            already released the gate and cleared `_is_running` for it).
            `False` when the run needs the normal DD-42 halt-outcome
            resolution, still owned by the caller's `_settle_run`.
        """
        toggles = self._resolve_phase_toggles(run)
        evaluators = self._make_evaluators_or_fail_run(
            run=run, toggles=toggles, lease=lease, dispatch_start_ms=dispatch_start_ms
        )
        if evaluators is None:
            return True
        tasks = self._tasks_store.list_tasks(run.run_id)
        tasks_by_id = {t.task_id: t for t in tasks}
        if self._probe_embeddings_if_needed(
            run=run,
            tasks=tasks,
            keyword_enabled=toggles.keyword_enabled,
            cosine_enabled=toggles.cosine_enabled,
            lease=lease,
            dispatch_start_ms=dispatch_start_ms,
        ):
            return True

        def _unit_factory_for_phase(
            phase: Phase, result: BenchmarkResult
        ) -> Callable[[], ResultPatch]:
            return self._build_unit(
                phase=phase,
                result=result,
                task=tasks_by_id[result.task_id],
                evaluators=evaluators,
                token=token,
                toggles=toggles,
            )

        run_all_phases(
            run_mode=run.run_mode,
            keyword_enabled=toggles.keyword_enabled,
            cosine_enabled=toggles.cosine_enabled,
            judge_enabled=toggles.judge_enabled,
            run_id=run.run_id,
            runner=self._task_runner,
            token=token,
            results_store=self._results_store,
            unit_factory_for_phase=_unit_factory_for_phase,
        )
        return False

    def _resolve_phase_toggles(self, run: BenchmarkRun) -> "_PhaseToggles":
        """Resolve this run's four `eval.*` grading toggles from its settings."""
        keyword_enabled = self._settings_service.get_bool("eval.phase_keyword_enabled", run=run)
        cosine_enabled = self._settings_service.get_bool("eval.phase_cosine_enabled", run=run)
        judge_enabled = (
            self._settings_service.get_bool("eval.phase_judge_enabled", run=run)
            if run.run_mode is RunMode.GRADED
            else False
        )
        force_judge = self._settings_service.get_bool("eval.force_judge_on_prior_failure", run=run)
        return _PhaseToggles(
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
            force_judge=force_judge,
        )

    def _make_evaluators_or_fail_run(
        self,
        *,
        run: BenchmarkRun,
        toggles: "_PhaseToggles",
        lease: GateLease,
        dispatch_start_ms: int,
    ) -> "_RunEvaluators | None":
        """Construct this run's evaluators; on a construction-time `AppError`, fail the run.

        `ProviderRegistry.get_client` (reached while resolving the judge
        client) can raise `ConfigurationError` here just as easily as inside
        a unit — this call happens before `run_all_phases` even starts, on
        the dispatcher thread, so nothing contains it unless this method
        does (DD-44). Rather than let it escape `_dispatch_run` uncaught,
        or crash via `ContractViolationError`, this treats it exactly like
        the embedding probe's own fail-fast path: the run settles `FAILED`
        as data, never a raise, and the gate/`_is_running` are released here
        since `_settle_run` will not run for this path (see `_run_phases`).

        Returns:
            The constructed `_RunEvaluators` on success; `None` once this
            call has already persisted `RunStatus.FAILED`, emitted
            `_run_failed`, and released the gate.
        """
        try:
            return _RunEvaluators(
                sanity_checker=make_sanity_checker(snapshot=run.settings_snapshot),
                keyword_evaluator=make_keyword_evaluator(
                    embedding_service=self._embedding_service, snapshot=run.settings_snapshot
                ),
                cosine_evaluator=make_cosine_evaluator(embedding_service=self._embedding_service),
                judge_evaluator=self._make_judge_evaluator_if_enabled(
                    run=run, judge_enabled=toggles.judge_enabled
                ),
            )
        except AppError as exc:
            if isinstance(exc, TaskCancelledError):
                raise
            self._fail_run(
                run=run,
                error_message=exc.message,
                lease=lease,
                dispatch_start_ms=dispatch_start_ms,
            )
            return None

    def _make_judge_evaluator_if_enabled(
        self, *, run: BenchmarkRun, judge_enabled: bool
    ) -> JudgeEvaluator | None:
        """Construct the run's `JudgeEvaluator`, or `None` when the judge phase is off.

        `judge_enabled and run.judge_provider_id is None` — the run's own
        judge-configuration is internally inconsistent — is treated as the
        same "not actually enabled" case, not an error: run-creation
        validation that `judge_enabled ⟹ judge_provider_id present` is
        explicitly out of this story's scope, so this method cannot assume
        that invariant. `phase_applies(JUDGE_CHECK)` only ever consults
        `judge_enabled`, so a caller relying on `judge_evaluator is None` to
        infer "the phase is skipped" would be wrong here — see
        `_build_judge_unit_for`'s defensive `ContractViolationError` for the
        backstop this leaves in place.
        """
        if not (judge_enabled and run.judge_provider_id is not None):
            return None
        judge_model_entry = next(m for m in run.models if m.role is ModelRole.JUDGE)
        judge_client = self._provider_registry.get_client(run.judge_provider_id)
        return make_judge_evaluator(
            llm_client=judge_client,
            model_name=judge_model_entry.model_name,
            snapshot=run.settings_snapshot,
        )

    def _probe_embeddings_if_needed(  # noqa: PLR0913  # every argument is a distinct
        # collaborator this fail-fast-or-continue check needs: the run/tasks/toggles it
        # decides from, plus the lease/dispatch_start_ms it must forward to `_fail_run`
        # on the failure path since `_settle_run` will not run for that path
        self,
        *,
        run: BenchmarkRun,
        tasks: tuple[BenchmarkTask, ...],
        keyword_enabled: bool,
        cosine_enabled: bool,
        lease: GateLease,
        dispatch_start_ms: int,
    ) -> bool:
        """Run the DD-48 fail-fast probe when needed; return `True` iff it failed.

        On failure, persists `RunStatus.FAILED` (with `run_analysis` naming
        the embedding pair), emits `_run_failed`, and releases the gate —
        all before any Phase-2 inference unit is submitted (STORY-029-AC-3).
        """
        has_golden_answer_task = any(t.golden_answer is not None for t in tasks)
        has_semantic_terms_task = any(t.required_terms.semantic for t in tasks)
        if not run_needs_embeddings(
            run_mode_graded=run.run_mode is RunMode.GRADED,
            cosine_enabled=cosine_enabled,
            has_golden_answer_task=has_golden_answer_task,
            keyword_enabled=keyword_enabled,
            has_semantic_terms_task=has_semantic_terms_task,
        ):
            return False
        probe_error = run_embedding_probe(embedding_service=self._embedding_service)
        if probe_error is None:
            return False
        self._fail_run(
            run=run, error_message=probe_error, lease=lease, dispatch_start_ms=dispatch_start_ms
        )
        return True

    def _fail_run(
        self, *, run: BenchmarkRun, error_message: str, lease: GateLease, dispatch_start_ms: int
    ) -> None:
        """Persist `RunStatus.FAILED`, emit `_run_failed`, and release the gate.

        The single early-halt path shared by every construction-time/
        pre-inference failure this lifecycle controller can hit outside the
        normal DD-42 halt-outcome resolution (`_settle_run` itself, reached
        only once `run_all_phases` has actually started). Both callers pass
        `lease`/`dispatch_start_ms` because this method — not `_settle_run`
        — owns releasing the gate and clearing `_is_running` for this path.
        """
        elapsed_ms = self._clock.monotonic_ms() - dispatch_start_ms
        self._runs_store.update_run_status(
            run.run_id,
            RunStatusPatch(
                status=RunStatus.FAILED, run_analysis=error_message, total_elapsed_ms=elapsed_ms
            ),
        )
        emit_run_failed(
            self._bus,
            RunFailedEvent(
                run_id=run.run_id,
                failed_at=self._clock.now_utc(),
                error_kind=ErrorKind.OTHER,
                error_message=error_message,
                completed_tasks=0,
                total_tasks=run.total_tasks,
            ),
        )
        self._release_gate_and_clear_running(lease)

    def _release_gate_and_clear_running(self, lease: GateLease) -> None:
        """Release the single-inference gate and clear `_is_running` (shared by
        `_settle_run` and `_fail_run`'s early-halt path — see Fix 1's report)."""
        self._inference_activity_store.release(lease)
        with self._lock:
            self._is_running = False

    def _build_unit(  # noqa: PLR0913  # each parameter is a distinct collaborator
        # this per-phase unit factory needs; the two dataclass bundles
        # (_RunEvaluators, _PhaseToggles) already group everything groupable —
        # phase/result/task/token are each independently varying per call
        self,
        *,
        phase: Phase,
        result: BenchmarkResult,
        task: BenchmarkTask,
        evaluators: "_RunEvaluators",
        token: CancellationToken,
        toggles: "_PhaseToggles",
    ) -> Callable[[], ResultPatch]:
        """Dispatch to the matching `build_*_unit` factory for one phase."""
        if phase is Phase.INFERENCE:
            return self._build_inference_unit_for(
                result=result, task=task, evaluators=evaluators, token=token, toggles=toggles
            )
        if phase is Phase.KEYWORD_CHECK:
            return build_keyword_unit(
                result=result,
                task=task,
                evaluator=evaluators.keyword_evaluator,
                cosine_enabled=toggles.cosine_enabled,
                judge_enabled=toggles.judge_enabled,
                force_judge_on_prior_failure=toggles.force_judge,
            )
        if phase is Phase.COSINE_CHECK:
            return build_cosine_unit(
                result=result,
                task=task,
                evaluator=evaluators.cosine_evaluator,
                judge_enabled=toggles.judge_enabled,
                force_judge_on_prior_failure=toggles.force_judge,
            )
        if phase is Phase.JUDGE_CHECK:
            return self._build_judge_unit_for(
                result=result, task=task, evaluators=evaluators, token=token, toggles=toggles
            )
        raise ContractViolationError(message=f"unreachable phase {phase!r}")

    def _build_inference_unit_for(
        self,
        *,
        result: BenchmarkResult,
        task: BenchmarkTask,
        evaluators: "_RunEvaluators",
        token: CancellationToken,
        toggles: "_PhaseToggles",
    ) -> Callable[[], ResultPatch]:
        """Build the Phase-2 unit, resolving its fixed per-attempt timeout budget."""
        timeout_ms = self._settings_service.get_int("benchmark.max_timeout_seconds") * 1000
        return build_inference_unit(
            result=result,
            task=task,
            provider_registry=self._provider_registry,
            sanity_checker=evaluators.sanity_checker,
            timeout_ms=timeout_ms,
            clock=self._clock,
            bus=self._bus,
            token=token,
            keyword_enabled=toggles.keyword_enabled,
            cosine_enabled=toggles.cosine_enabled,
            judge_enabled=toggles.judge_enabled,
        )

    def _build_judge_unit_for(
        self,
        *,
        result: BenchmarkResult,
        task: BenchmarkTask,
        evaluators: "_RunEvaluators",
        token: CancellationToken,
        toggles: "_PhaseToggles",
    ) -> Callable[[], ResultPatch]:
        """Build the Phase-5 unit, resolving its fixed per-attempt timeout budget.

        `evaluators.judge_evaluator is None` here should be unreachable in
        practice: `_make_judge_evaluator_if_enabled` only returns `None` when
        `judge_enabled` is false or `judge_provider_id` is absent, and either
        condition already makes `phase_applies(JUDGE_CHECK)` false, so
        `run_all_phases` never dispatches a JUDGE_CHECK unit for this run at
        all. The `ContractViolationError` below is kept only as a defensive
        backstop for a future change that decouples those two checks — it is
        not this story's primary handling for "judge enabled, no client":
        that case is caught earlier, in `_make_evaluators_or_fail_run`,
        which settles the run `FAILED` as data before dispatch ever starts.
        """
        if evaluators.judge_evaluator is None:
            raise ContractViolationError(
                message="unreachable: JUDGE_CHECK unit requested but judge_evaluator is "
                "None (phase_applies already guarantees judge_enabled implies this)"
            )
        timeout_ms = self._settings_service.get_int("eval.judge_timeout_max_seconds") * 1000
        return build_judge_unit(
            result=result,
            task=task,
            evaluator=evaluators.judge_evaluator,
            timeout_ms=timeout_ms,
            token=token,
            bus=self._bus,
            force_judge_on_prior_failure=toggles.force_judge,
        )

    def _settle_run(
        self,
        *,
        run: BenchmarkRun,
        token: CancellationToken,
        lease: GateLease,
        dispatch_start_ms: int,
    ) -> None:
        """Resolve the DD-42 outcome from one snapshot, persist, emit, release the gate."""
        level, reason = token.snapshot()
        current_rows = self._results_store.list_results(run.run_id)
        all_completed = all(row.status is ResultStatus.COMPLETED for row in current_rows)
        outcome = resolve_halt_outcome(level=level, reason=reason, all_rows_completed=all_completed)
        completed_count = sum(1 for row in current_rows if row.status not in _NON_TERMINAL_STATUSES)
        elapsed_ms = self._clock.monotonic_ms() - dispatch_start_ms
        if outcome.persisted_status is not None:
            self._runs_store.update_run_status(
                run.run_id,
                RunStatusPatch(
                    status=outcome.persisted_status,
                    completed_tasks=completed_count,
                    total_elapsed_ms=elapsed_ms,
                    finished_at=self._clock.now_utc(),
                ),
            )
        self._emit_settle_event(
            run=run,
            outcome_parked_paused=outcome.parked_paused,
            persisted_status=outcome.persisted_status,
            completed_count=completed_count,
            elapsed_ms=elapsed_ms,
            current_rows=current_rows,
        )
        self._release_gate_and_clear_running(lease)

    def _emit_settle_event(  # noqa: PLR0913  # one parameter per distinct input the
        # three mutually-exclusive terminal-event branches need
        self,
        *,
        run: BenchmarkRun,
        outcome_parked_paused: bool,
        persisted_status: RunStatus | None,
        completed_count: int,
        elapsed_ms: int,
        current_rows: tuple[BenchmarkResult, ...],
    ) -> None:
        """Emit exactly the one terminal/park event this halt's outcome calls for."""
        if outcome_parked_paused:
            emit_run_paused(
                self._bus,
                RunPausedEvent(
                    run_id=run.run_id,
                    paused_at=self._clock.now_utc(),
                    completed_tasks=completed_count,
                    total_tasks=run.total_tasks,
                ),
            )
        elif persisted_status is RunStatus.STOPPED:
            emit_run_stopped(
                self._bus,
                RunStoppedEvent(
                    run_id=run.run_id,
                    stopped_at=self._clock.now_utc(),
                    completed_tasks=completed_count,
                    total_tasks=run.total_tasks,
                ),
            )
        elif persisted_status is RunStatus.COMPLETED:
            counts_by_status: dict[ResultStatus, int] = {}
            for row in current_rows:
                counts_by_status[row.status] = counts_by_status.get(row.status, 0) + 1
            emit_run_finished(
                self._bus,
                RunFinishedEvent(
                    run_id=run.run_id,
                    finished_at=self._clock.now_utc(),
                    run_status=RunStatus.COMPLETED,
                    total_tasks=run.total_tasks,
                    completed_tasks=completed_count,
                    counts_by_result_status=counts_by_status,
                    total_elapsed_ms=elapsed_ms,
                ),
            )


def _assert_protocol_conformance(impl: _BenchmarkFlowApiImpl) -> BenchmarkFlowApi:
    """Static-typing helper: assert `_BenchmarkFlowApiImpl` satisfies `BenchmarkFlowApi`."""
    return impl
