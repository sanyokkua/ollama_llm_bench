"""Proves: STORY-085-AC-5, STORY-085-AC-6

Run-start task staging: a run started through `BenchmarkFlowApi.start` persists
the tasks its `RunStartRequest` names, so `TasksStore.list_tasks(run_id)` is
non-empty for the first time in production.

These drive the real `start()` path against a recording `TasksStore` and the
real `make_run_task_stager` collaborators, but hand `start()` a dispatcher that
never runs the submitted loop -- the acceptance criteria are about what run
creation persists, not about executing the run.
"""

from collections.abc import Callable
from pathlib import Path

from ollama_llm_bench.backend.benchmark_pipeline import (
    BenchmarkFlowApi,
    make_benchmark_pipeline,
    make_run_task_stager,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import _RecordingEventBus
from ollama_llm_bench.backend.domain.models import (
    BenchmarkTask,
    ModelDescriptor,
    PerformanceConfig,
    RunId,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.events import SIGNAL_RUN_START_FAILED
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.performance_task_generator import make_performance_task_generator
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore
from ollama_llm_bench.backend.task_files import make_task_file_loader

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_NO_RUN_CREATED = 0

_TASK_FILE_TEMPLATE = """schema_version: 1
tasks:
  - task_id: {task_id}
    question: {question}
    golden_answer: {golden_answer}
"""


class _RecordingTasksStore:
    """A `TasksStore` double that really stores, ordered by `task_order`.

    The package's shared `fake_tasks_store` is a `Mock(spec=TasksStore)` whose
    `create_tasks` discards its argument, which is exactly wrong for a test
    about what run creation writes.
    """

    def __init__(self) -> None:
        self._by_run: dict[RunId, tuple[BenchmarkTask, ...]] = {}

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        self._by_run[run_id] = self._by_run.get(run_id, ()) + tasks

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return tuple(sorted(self._by_run.get(run_id, ()), key=lambda task: task.task_order))


class _NeverRunsDispatcher:
    """A `RunDispatcher` double that accepts the dispatch loop and never runs it.

    Keeps these tests scoped to run *creation*: `start()` returns having
    persisted the run header, its tasks and its initial result rows, with no
    provider call and no phase execution.
    """

    def submit(self, fn: Callable[[], None]) -> None:
        del fn

    def shutdown(self, timeout_ms: int) -> None:
        del timeout_ms


def _write_task_file(path: Path, *, task_id: str, question: str, golden_answer: str) -> str:
    path.write_text(
        _TASK_FILE_TEMPLATE.format(task_id=task_id, question=question, golden_answer=golden_answer),
        encoding="utf-8",
    )
    return str(path)


def _make_pipeline(  # noqa: PLR0913  # test wiring must name every fixture collaborator
    *,
    tasks_store: _RecordingTasksStore,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> BenchmarkFlowApi:
    """Wire the real pipeline with the real stager over the real generator/loader."""
    return make_benchmark_pipeline(
        results_store=fake_results_store,
        runs_store=fake_runs_store,
        tasks_store=tasks_store,
        task_stager=make_run_task_stager(
            performance_task_generator=make_performance_task_generator(),
            task_file_loader=make_task_file_loader(),
        ),
        inference_activity_store=fake_inference_activity_store,
        task_runner=inline_task_runner,  # type: ignore[arg-type]  # fixture is TaskRunner[ResultPatch]
        run_dispatcher=_NeverRunsDispatcher(),
        bus=fake_event_bus,  # type: ignore[arg-type]  # fixture satisfies EventBus structurally
        clock=fake_clock,
        embedding_service=fake_embedding_service,
        provider_registry=fake_provider_registry,
        settings_service=fake_settings_service,
        run_snapshot_builder=fake_run_snapshot_builder,
    )


def test_synthetic_run_stages_one_task_per_grid_cell(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-085-AC-5

    A SYNTHETIC run started from a RunStartRequest carrying a 2x3 size matrix
    with 2 repeats persists exactly 12 tasks -- one per (input size x output
    size x repeat) -- and each grid cell is a distinct task_id.
    """
    # Arrange
    tasks_store = _RecordingTasksStore()
    pipeline = _make_pipeline(
        tasks_store=tasks_store,
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )
    request = RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
        performance_config=PerformanceConfig(
            input_sizes=(64, 256), output_sizes=(64, 256, 1024), repeats=2
        ),
    )

    # Act
    run_id = pipeline.start(request)

    # Assert
    staged = tasks_store.list_tasks(run_id)
    assert len(staged) == 2 * 3 * 2
    assert len({task.task_id for task in staged}) == 2 * 3 * 2


def test_tasks_mode_stages_tasks_from_every_task_path(  # noqa: PLR0913
    tmp_path: Path,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-085-AC-6

    A TASKS run whose task_paths names two readable files holding disjoint
    tasks persists every task from both files, in task_paths order.
    """
    # Arrange
    first = _write_task_file(
        tmp_path / "first.yaml",
        task_id="from_first_file",
        question="What is the capital of France?",
        golden_answer="Paris",
    )
    second = _write_task_file(
        tmp_path / "second.yaml",
        task_id="from_second_file",
        question="What is the capital of Japan?",
        golden_answer="Tokyo",
    )
    tasks_store = _RecordingTasksStore()
    pipeline = _make_pipeline(
        tasks_store=tasks_store,
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )
    request = RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
        task_paths=(first, second),
    )

    # Act
    run_id = pipeline.start(request)

    # Assert
    assert [task.task_id for task in tasks_store.list_tasks(run_id)] == [
        "from_first_file",
        "from_second_file",
    ]


def test_duplicate_task_id_across_files_keeps_the_first_occurrence(  # noqa: PLR0913
    tmp_path: Path,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-085-AC-6

    Two files declaring the same task_id stage one task, carrying the earlier
    path's question -- mirroring the loader's own within-file duplicate rule
    rather than letting the same id reach TasksStore twice.
    """
    # Arrange
    first = _write_task_file(
        tmp_path / "first.yaml",
        task_id="shared_id",
        question="What is the capital of France?",
        golden_answer="Paris",
    )
    second = _write_task_file(
        tmp_path / "second.yaml",
        task_id="shared_id",
        question="What is the capital of Japan?",
        golden_answer="Tokyo",
    )
    tasks_store = _RecordingTasksStore()
    pipeline = _make_pipeline(
        tasks_store=tasks_store,
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )
    request = RunStartRequest(
        run_mode=RunMode.GRADED,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
        task_paths=(first, second),
    )

    # Act
    run_id = pipeline.start(request)

    # Assert
    staged = tasks_store.list_tasks(run_id)
    assert len(staged) == 1
    assert staged[0].question == "What is the capital of France?"


def test_unreadable_task_path_rejects_the_start_without_raising(  # noqa: PLR0913
    tmp_path: Path,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: _RecordingEventBus,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-085 Definition of done

    A task_paths entry the loader rejects outright never propagates out of
    start() (the pipeline never raises to its caller). It is surfaced as
    _run_start_failed, creates no run header, and hands the single-inference
    gate back so the next start can acquire it.
    """
    # Arrange -- a non-YAML extension is a whole-file TaskFileError by contract
    tasks_store = _RecordingTasksStore()
    pipeline = _make_pipeline(
        tasks_store=tasks_store,
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )
    request = RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
        task_paths=(str(tmp_path / "not-a-task-file.txt"),),
    )

    # Act -- no pytest.raises: an escaping TaskFileError would fail the test here
    run_id = pipeline.start(request)

    # Assert
    assert run_id == _NO_RUN_CREATED
    assert fake_event_bus.emitted_signal_names() == [SIGNAL_RUN_START_FAILED]
    assert fake_runs_store.create_run.call_count == 0  # type: ignore[attr-defined]  # Mock(spec=RunsStore)
    assert fake_inference_activity_store.release.call_count == 1  # type: ignore[attr-defined]  # Mock(spec=...)
