"""Proves: STORY-029-AC-3, STORY-029-AC-7 (final-review fixes: FAILED status is never
overwritten to STOPPED, and DD-44 containment reaches construction-time `AppError`s
raised before `run_all_phases` ever starts — not just per-unit failures)."""

import time

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import StagesNoTasks, make_task
from ollama_llm_bench.backend.domain.models import (
    ModelDescriptor,
    RequiredTerms,
    ResultStatus,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_WAIT_TIMEOUT_S = 2.0
_POLL_INTERVAL_S = 0.01


def _make_graded_run_start_request() -> RunStartRequest:
    """A GRADED-mode request naming one test target — cosine/keyword toggles are
    resolved from `fake_settings_service`, not from this request."""
    return RunStartRequest(
        run_mode=RunMode.GRADED,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _wait_until_idle(pipeline: BenchmarkFlowApi, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` from the test's own thread until the dispatcher settles."""
    deadline = time.monotonic() + timeout_s
    while pipeline.is_running() and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
    assert not pipeline.is_running(), "pipeline did not settle within the timeout"


def _make_pipeline(  # noqa: PLR0913  # test wiring must name every fixture collaborator
    *,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> BenchmarkFlowApi:
    return make_benchmark_pipeline(
        results_store=fake_results_store,
        runs_store=fake_runs_store,
        tasks_store=fake_tasks_store,
        task_stager=StagesNoTasks(),
        inference_activity_store=fake_inference_activity_store,
        task_runner=inline_task_runner,  # type: ignore[arg-type]  # fixture is TaskRunner[ResultPatch]
        run_dispatcher=inline_run_dispatcher,  # type: ignore[arg-type]  # fixture is RunDispatcher
        bus=fake_event_bus,  # type: ignore[arg-type]  # fixture satisfies EventBus structurally
        clock=fake_clock,
        embedding_service=fake_embedding_service,
        provider_registry=fake_provider_registry,
        settings_service=fake_settings_service,
        run_snapshot_builder=fake_run_snapshot_builder,
    )


def test_failed_embedding_probe_settles_failed_not_overwritten_to_stopped(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-3 (final-review Fix 1 + Fix 4)

    A failed run-start embedding probe must settle the run `FAILED`, with
    `run_analysis` naming the embedding pair — `_settle_run`'s own DD-42
    halt-outcome resolution must NEVER run afterwards and overwrite that
    `FAILED` status to `STOPPED` (the token was never cancelled; all rows
    are still `PENDING`, so `resolve_halt_outcome` would otherwise resolve
    `STOPPED`). Also proves the gate is released and `is_running()` clears
    even though `_settle_run` itself never ran for this path.
    """
    task_one = make_task(task_id="task-1", golden_answer="Paris", required_terms=RequiredTerms())
    fake_tasks_store.list_tasks.return_value = (task_one,)  # type: ignore[attr-defined]
    fake_settings_service.get_bool.return_value = True  # type: ignore[attr-defined]  # cosine_enabled=True etc.

    def _empty_embed(text: str) -> tuple[float, ...]:
        del text
        return ()

    fake_embedding_service.embed = _empty_embed  # type: ignore[method-assign]

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.start(_make_graded_run_start_request())
    _wait_until_idle(pipeline)

    # The LAST update_run_status call is the one that matters: it must still
    # say FAILED with the probe's error message on run_analysis, never a
    # later STOPPED overwrite from a wrongly-invoked _settle_run.
    calls = fake_runs_store.update_run_status.call_args_list  # type: ignore[attr-defined]
    last_run_id, last_patch = calls[-1].args
    assert last_run_id == 1
    assert last_patch.status.value == "failed"
    assert last_patch.run_analysis is not None
    assert "embed" in last_patch.run_analysis.lower()
    assert "_run_failed" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
    assert "_run_stopped" not in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
    remaining_rows = fake_results_store.list_results(1)
    assert remaining_rows[0].status is ResultStatus.PENDING
    fake_inference_activity_store.release.assert_called_once()  # type: ignore[attr-defined]


def test_inference_unit_provider_registry_error_is_contained_never_raises(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029 final-review Fix 2 (DD-44 containment gap in
    `build_inference_unit`)

    `ProviderRegistry.get_client` raising `ConfigurationError` for the
    inference unit's own provider — e.g. the provider was disabled between
    run creation and this unit's execution — must never escape `start()`.
    The row settles to the leaf's own DD-44 terminal status (ERRORED, since
    `ConfigurationError` carries no per-unit `terminal_result_status`), and
    the run itself completes normally rather than crashing the dispatcher.
    """
    task_one = make_task(task_id="task-1")
    fake_tasks_store.list_tasks.return_value = (task_one,)  # type: ignore[attr-defined]
    fake_provider_registry.get_client.side_effect = ConfigurationError(  # type: ignore[attr-defined]
        message="provider disabled"
    )

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    # start() itself must not raise — this is the crux of the DD-44 assertion.
    pipeline.start(
        RunStartRequest(
            run_mode=RunMode.TASKS,
            test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
        )
    )
    _wait_until_idle(pipeline)

    remaining_rows = fake_results_store.list_results(1)
    assert len(remaining_rows) == 1
    assert remaining_rows[0].status is ResultStatus.ERRORED
    assert remaining_rows[0].error_message == "provider disabled"
    assert not pipeline.is_running()


def test_judge_enabled_with_unresolvable_client_settles_run_failed_not_crash(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029 final-review Fix 3

    A run with the judge phase enabled (`eval.phase_judge_enabled=True`) whose
    judge provider cannot be resolved into a live client (`get_client` raises
    `ConfigurationError`, e.g. its API key env var is unset) must settle the
    run as data — persisted `RunStatus.FAILED` plus a `_run_failed` event —
    rather than reach `_build_judge_unit_for`'s defensive
    `ContractViolationError` and crash the process. This is caught at
    evaluator-construction time, before any Phase-2 inference unit is even
    submitted.
    """
    task_one = make_task(task_id="task-1")
    fake_tasks_store.list_tasks.return_value = (task_one,)  # type: ignore[attr-defined]
    fake_settings_service.get_bool.return_value = True  # type: ignore[attr-defined]  # judge_enabled, etc.
    fake_provider_registry.get_client.side_effect = ConfigurationError(  # type: ignore[attr-defined]
        message="judge provider misconfigured"
    )

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.start(
        RunStartRequest(
            run_mode=RunMode.GRADED,
            test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
            judge_model=ModelDescriptor(provider_id=_PROVIDER_ID, model_name="judge-model"),
        )
    )
    _wait_until_idle(pipeline)

    calls = fake_runs_store.update_run_status.call_args_list  # type: ignore[attr-defined]
    last_run_id, last_patch = calls[-1].args
    assert last_run_id == 1
    assert last_patch.status.value == "failed"
    assert last_patch.run_analysis == "judge provider misconfigured"
    assert "_run_failed" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
    remaining_rows = fake_results_store.list_results(1)
    assert remaining_rows[0].status is ResultStatus.PENDING
    assert not pipeline.is_running()
