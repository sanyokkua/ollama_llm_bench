"""Public factories for the UI adapter gateways (``01_MODULE_INVENTORY.md`` §5, ADR-0014).

Constructs the concrete ``MainWindowGateway`` over ``AppSettingsStore``,
``SettingsService``, ``ReadinessService``, ``BenchmarkFlowApi``, and ``RunDispatcher``,
the concrete ``NewBenchmarkGateway`` over ``AppSettingsStore``, ``SettingsService``,
``ProviderRegistry``, ``ReadinessService``, ``BenchmarkFlowApi``, and
``NotificationService``, the concrete ``ProgressGateway`` over ``BenchmarkFlowApi``,
``RunsStore``, ``ResultsStore``, ``AppSettingsStore``, ``SettingsService``,
``PlatformDetector``, a ``TaskRunner``, a ``Clock``, and the two adapter-local
manual-probe/run-log-write-status collaborators, and the concrete ``ResumeGateway``
over ``RunsStore``, ``ResultsStore``, ``TasksStore``, ``AppSettingsStore``,
``ReadinessService``, ``ProvidersStore``, ``ProviderRegistry``, ``RunDriftDetector``,
``BenchmarkFlowApi``, ``TableSerializer``, and a ``Clock`` -- the adapters that let the
Main Window shell,
the New Benchmark widget, the Progress widget, and the Resume Benchmark widget reach
the backend without ever holding a backend Store or Service Protocol themselves
(D-R-06).
"""

import icontract

from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.ui_gateways._internal.main_window.gateway import (
    MainWindowGatewayCollaborators,
    _MainWindowGateway,
)
from ollama_llm_bench.adapters.ui_gateways._internal.new_benchmark.gateway import (
    NewBenchmarkGatewayCollaborators,
    _NewBenchmarkGateway,
)
from ollama_llm_bench.adapters.ui_gateways._internal.progress.gateway import (
    ProgressGatewayCollaborators,
    _ProgressGateway,
)
from ollama_llm_bench.adapters.ui_gateways._internal.result.gateway import (
    ResultGatewayCollaborators,
    _ResultGateway,
)
from ollama_llm_bench.adapters.ui_gateways._internal.resume.gateway import (
    ResumeGatewayCollaborators,
    _ResumeGateway,
)
from ollama_llm_bench.adapters.ui_gateways.protocols import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
    MainWindowGateway,
    ManualProviderProbeCommand,
    NewBenchmarkGateway,
    ProgressGateway,
    ResultGateway,
    ResumeGateway,
    RunLogWriteStatus,
)
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.charts import ChartAggregator
from ollama_llm_bench.backend.concurrency import RunDispatcher, TaskRunner
from ollama_llm_bench.backend.csv_export import TableSerializer
from ollama_llm_bench.backend.infra.protocols import Clock, PlatformDetector
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.persistence.tasks import TasksStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.run_analysis import RunAnalysisService
from ollama_llm_bench.backend.run_drift import RunDriftDetector
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "JudgeAnalysisGenerationOutcome",
    "JudgeAnalysisGenerationResult",
    "MainWindowGateway",
    "ManualProviderProbeCommand",
    "NewBenchmarkGateway",
    "ProgressGateway",
    "ResultGateway",
    "ResumeGateway",
    "RunLogWriteStatus",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
    "make_progress_gateway",
    "make_result_gateway",
    "make_resume_gateway",
]


@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda readiness: readiness is not None,
    "readiness is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda flow: flow is not None,
    "flow is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda dispatcher: dispatcher is not None,
    "dispatcher is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_main_window_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_main_window_gateway(
    *,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    readiness: ReadinessService,
    flow: BenchmarkFlowApi,
    dispatcher: RunDispatcher,
) -> MainWindowGateway:
    """Construct the Main Window's adapter gateway.

    Construction is side-effect free: it performs no backend read, no readiness
    probe, and no network call (STORY-105-AC-3).

    Args:
        app_settings: The user-saved settings store the nullable window-shell
            reads (geometry, splitter sizes, active workspace) go through.
        settings: The settings service the window-shell writes and the
            resolved theme read go through, so the settings-changed event
            fires on every write.
        readiness: The readiness service backing the status-bar health dot's
            snapshot read and re-probe trigger.
        flow: The benchmark flow API backing the quit decision and the
            graceful shutdown on application quit.
        dispatcher: The single, persistent pipeline-dispatcher thread that a
            re-probe is submitted to -- never the ``TaskRunner`` pool.

    Returns:
        A ``MainWindowGateway`` ready to be handed to ``make_main_window``.
    """
    return _MainWindowGateway(
        collaborators=MainWindowGatewayCollaborators(
            app_settings=app_settings,
            settings=settings,
            readiness=readiness,
            flow=flow,
            dispatcher=dispatcher,
        )
    )


@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda provider_registry: provider_registry is not None,
    "provider_registry is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda readiness: readiness is not None,
    "readiness is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda flow: flow is not None,
    "flow is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda notification: notification is not None,
    "notification is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_new_benchmark_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_new_benchmark_gateway(  # noqa: PLR0913  # six distinct required collaborators
    # per the approved D-R-06 gateway shape (STORY-106)
    *,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    provider_registry: ProviderRegistry,
    readiness: ReadinessService,
    flow: BenchmarkFlowApi,
    notification: NotificationService,
) -> NewBenchmarkGateway:
    """Construct the New Benchmark widget's adapter gateway.

    Construction is side-effect free: it performs no backend read, no readiness
    probe, and no network call (STORY-106-AC-4).

    Args:
        app_settings: The user-saved settings store the nullable
            advanced-option-default/``benchmark.last_mode``/
            ``embedding.hide_from_test_models`` reads go through.
        settings: The settings service writes go through, so the
            settings-changed event fires on every write.
        provider_registry: The provider registry backing the model picker's
            enabled-provider list.
        readiness: The readiness service backing the pre-run readiness gate's
            snapshot read.
        flow: The benchmark flow API backing the run-start command.
        notification: The notification service backing the preflight-refusal
            toast.

    Returns:
        A ``NewBenchmarkGateway`` ready to be handed to
        ``make_new_benchmark_widget``.
    """
    return _NewBenchmarkGateway(
        collaborators=NewBenchmarkGatewayCollaborators(
            app_settings=app_settings,
            settings=settings,
            provider_registry=provider_registry,
            readiness=readiness,
            flow=flow,
            notification=notification,
        )
    )


@icontract.require(
    lambda flow: flow is not None, "flow is a required collaborator wired by compose.py"
)
@icontract.require(
    lambda runs_store: runs_store is not None,
    "runs_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda results_store: results_store is not None,
    "results_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda platform_detector: platform_detector is not None,
    "platform_detector is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda task_runner: task_runner is not None,
    "task_runner is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda clock: clock is not None, "clock is a required collaborator wired by compose.py"
)
@icontract.require(
    lambda probe_command: probe_command is not None,
    "probe_command is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda write_status: write_status is not None,
    "write_status is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_progress_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_progress_gateway(  # noqa: PLR0913  # ten distinct required collaborators per the
    # approved D-R-06 gateway shape (STORY-107)
    *,
    flow: BenchmarkFlowApi,
    runs_store: RunsStore,
    results_store: ResultsStore,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    platform_detector: PlatformDetector,
    task_runner: TaskRunner[object],
    clock: Clock,
    probe_command: ManualProviderProbeCommand,
    write_status: RunLogWriteStatus,
) -> ProgressGateway:
    """Construct the Progress widget's adapter gateway.

    Construction is side-effect free: it performs no backend read, no probe, and
    no network call (STORY-107-AC-4).

    Args:
        flow: The benchmark flow API backing pause/resume/stop and the
            run-active query.
        runs_store: The run-header store backing run-metadata/rename/header
            reads and the run list.
        results_store: The per-task result-row store backing the counters read.
        app_settings: The user-saved settings store the nullable
            ``ui.run_log_verbosity``/``ui.auto_scroll_run_log`` reads go through.
        settings: The settings service writes go through, so the
            settings-changed event fires on every write.
        platform_detector: Resolves the application-data root the run-log
            directory is read from for past-run replay.
        task_runner: The scheduling port the manual provider probe is
            submitted to, off the graphical thread.
        clock: Supplies a fresh ``CancellationToken`` for each manual probe.
        probe_command: The collaborator that performs one provider health
            probe when submitted.
        write_status: The collaborator answering whether the run-log file
            writer's most recent write attempt failed.

    Returns:
        A ``ProgressGateway`` ready to be handed to ``make_progress_widget``
        (STORY-077).
    """
    return _ProgressGateway(
        collaborators=ProgressGatewayCollaborators(
            flow=flow,
            runs_store=runs_store,
            results_store=results_store,
            app_settings=app_settings,
            settings=settings,
            platform_detector=platform_detector,
            task_runner=task_runner,
            clock=clock,
            probe_command=probe_command,
            write_status=write_status,
        )
    )


@icontract.require(
    lambda runs_store: runs_store is not None,
    "runs_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda results_store: results_store is not None,
    "results_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda tasks_store: tasks_store is not None,
    "tasks_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda run_analysis: run_analysis is not None,
    "run_analysis is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda gate: gate is not None, "gate is a required collaborator wired by compose.py"
)
@icontract.require(
    lambda provider_registry: provider_registry is not None,
    "provider_registry is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda chart: chart is not None, "chart is a required collaborator wired by compose.py"
)
@icontract.require(
    lambda serializer: serializer is not None,
    "serializer is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda task_runner: task_runner is not None,
    "task_runner is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda clock: clock is not None, "clock is a required collaborator wired by compose.py"
)
@icontract.ensure(
    lambda result: result is not None,
    "make_result_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_result_gateway(  # noqa: PLR0913  # twelve distinct required collaborators per the
    # approved D-R-06 gateway shape (STORY-108)
    *,
    runs_store: RunsStore,
    results_store: ResultsStore,
    tasks_store: TasksStore,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    run_analysis: RunAnalysisService,
    gate: InferenceActivityStore,
    provider_registry: ProviderRegistry,
    chart: ChartAggregator,
    serializer: TableSerializer,
    task_runner: TaskRunner[object],
    clock: Clock,
) -> ResultGateway:
    """Construct the Result widget's adapter gateway.

    Construction is side-effect free: it performs no backend read, no probe, and
    no network call (STORY-108-AC-5).

    Args:
        runs_store: The run-header store backing the run-selector list, the
            single-run header read, the ``run_analysis`` persistence write,
            and the run metadata ``chart_data``/``serialize_table`` load.
        results_store: The per-task result-row store backing the results
            read, and the Summary/Details export aggregation.
        tasks_store: The frozen per-run task-metadata store backing the tasks
            read, and the Details export's ``tasks_by_id`` lookup.
        app_settings: The user-saved settings store the nullable
            ``ui.last_result_tab``/``ui.export_save_directly``/
            ``ui.score_display_format``/``eval.min_sample_size`` reads go
            through.
        settings: The settings service writes go through, so the
            settings-changed event fires on every write.
        run_analysis: The service ``regenerate_run_analysis`` dispatches to a
            worker thread; never invoked with ``inside_pipeline=True`` (that
            keyword is reserved for the benchmark pipeline's own call site).
        gate: The application-wide single-inference gate;
            ``regenerate_run_analysis`` performs a fast busy pre-check
            against it before dispatching.
        provider_registry: Resolves the analysis provider's current display
            name once ``regenerate_run_analysis`` completes with a
            ``GENERATED`` outcome.
        chart: The chart-aggregation service backing ``chart_data``.
        serializer: The table-serialization service backing
            ``serialize_table``.
        task_runner: The scheduling port ``regenerate_run_analysis``'s
            worker call is submitted to, off the graphical thread.
        clock: Supplies a fresh ``CancellationToken`` for the worker call and
            the export timestamp.

    Returns:
        A ``ResultGateway`` ready to be handed to ``make_result_widget``
        (STORY-077).
    """
    return _ResultGateway(
        collaborators=ResultGatewayCollaborators(
            runs_store=runs_store,
            results_store=results_store,
            tasks_store=tasks_store,
            app_settings=app_settings,
            settings=settings,
            run_analysis=run_analysis,
            gate=gate,
            provider_registry=provider_registry,
            chart=chart,
            serializer=serializer,
            task_runner=task_runner,
            clock=clock,
        )
    )


@icontract.require(
    lambda runs_store: runs_store is not None,
    "runs_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda results_store: results_store is not None,
    "results_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda tasks_store: tasks_store is not None,
    "tasks_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda readiness: readiness is not None,
    "readiness is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda providers_store: providers_store is not None,
    "providers_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda provider_registry: provider_registry is not None,
    "provider_registry is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda detector: detector is not None,
    "detector is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda flow: flow is not None, "flow is a required collaborator wired by compose.py"
)
@icontract.require(
    lambda serializer: serializer is not None,
    "serializer is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda clock: clock is not None, "clock is a required collaborator wired by compose.py"
)
@icontract.ensure(
    lambda result: result is not None,
    "make_resume_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_resume_gateway(  # noqa: PLR0913  # eleven distinct required collaborators per
    # the approved D-R-06 gateway shape (STORY-109)
    *,
    runs_store: RunsStore,
    results_store: ResultsStore,
    tasks_store: TasksStore,
    app_settings: AppSettingsStore,
    readiness: ReadinessService,
    providers_store: ProvidersStore,
    provider_registry: ProviderRegistry,
    detector: RunDriftDetector,
    flow: BenchmarkFlowApi,
    serializer: TableSerializer,
    clock: Clock,
) -> ResumeGateway:
    """Construct the Resume Benchmark widget's adapter gateway.

    Construction is side-effect free: it performs no backend read, no probe, and
    no network call (STORY-109-AC-5).

    Args:
        runs_store: The run-header store backing the run table, Clone, rename,
            delete, and status-patch operations.
        results_store: The per-task result-row store backing the results
            read, the resumable-results read, the whole-task/retry resets,
            Clone's result-row insert, and the Summary/Details export
            aggregation.
        tasks_store: The frozen per-run task-metadata store backing the tasks
            read, Clone's task-row insert, and the Details export's
            ``tasks_by_id`` lookup.
        app_settings: The settings store the sort-column/descending-flag read
            and write go through directly -- no registry entry exists for
            either raw key, so this bypasses ``SettingsService``.
        readiness: The readiness service ``detect_drift`` re-probes before
            comparing the run's frozen snapshot.
        providers_store: Resolves ``detect_drift``'s full live-provider
            catalog (enabled and disabled alike) -- the provider-drift check
            itself distinguishes a removed provider from a merely-disabled
            one by that flag, so an enabled-only subset would make the
            disabled case unreachable.
        provider_registry: Resolves each reachable provider's client for
            ``detect_drift``'s model-availability check.
        detector: The Run Drift Detector ``detect_drift`` delegates the pure
            comparison to.
        flow: The benchmark flow API backing the resume command and the
            run-active/active-run-id queries.
        serializer: The table-serialization service backing
            ``serialize_table``.
        clock: Supplies the export timestamp.

    Returns:
        A ``ResumeGateway`` ready to be handed to ``make_resume_benchmark_widget``
        (STORY-077).
    """
    return _ResumeGateway(
        collaborators=ResumeGatewayCollaborators(
            runs_store=runs_store,
            results_store=results_store,
            tasks_store=tasks_store,
            app_settings=app_settings,
            readiness=readiness,
            providers_store=providers_store,
            provider_registry=provider_registry,
            detector=detector,
            flow=flow,
            serializer=serializer,
            clock=clock,
        )
    )
