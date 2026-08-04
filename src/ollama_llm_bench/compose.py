"""The single composition root (STORY-077). ``build_app(*, app, loop) -> AppHandle`` wires
the whole object graph by hand, in the fixed order of
``16_Engineering_Standards/01_PROJECT_STRUCTURE.md`` §7, and returns an ``AppHandle``
carrying the shown window and a full 5-step ``shutdown()`` handle for ordered process termination.
Construction is synchronous and issues no network call. Keyword-argument-heavy
factory calls are pinned to one physical line each via ``# fmt: skip`` (E501 is
unenforced, see ``rules/formatting.md``).
"""

import contextlib
import functools
import importlib.metadata
import sqlite3
import sys
import threading
from typing import TYPE_CHECKING, NoReturn

import httpx
import msgspec
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import (  # fmt: skip
    QApplication,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QWidget,
)
import structlog

if TYPE_CHECKING:
    from collections.abc import Mapping

from ollama_llm_bench._compose_shims import (  # fmt: skip
    _AlwaysOkRunLogWriteStatus,
    _ExportFilenameBridge,
    _NoActiveRunTaskPaths,
    _NoModelFetcher,
    _NoOpManualProviderProbeCommand,
    _NoRunValidator,
    _NullEmbeddingClient,
    _ReadinessEmbeddingSelector,
)
from ollama_llm_bench.adapters.clipboard import Clipboard, make_clipboard
from ollama_llm_bench.adapters.file_system_actions import (  # fmt: skip
    make_file_change_watcher,
    make_file_system_actions,
)
from ollama_llm_bench.adapters.native_pickers import make_native_pickers
from ollama_llm_bench.adapters.notification_service import make_notification_service
from ollama_llm_bench.adapters.qt_benchmark_flow import (  # fmt: skip
    QtBenchmarkFlow,
    make_qt_benchmark_flow,
    make_run_dispatcher,
)
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.adapters.qt_runnables import QtTaskRunner, make_qt_task_runner
from ollama_llm_bench.adapters.ui_gateways import (  # fmt: skip
    make_main_window_gateway,
    make_new_benchmark_gateway,
    make_progress_gateway,
    make_result_gateway,
    make_resume_gateway,
    make_settings_gateway,
    make_task_editor_gateway,
)
from ollama_llm_bench.adapters.workspace_controller import make_workspace_controller
from ollama_llm_bench.backend import mode_visibility
from ollama_llm_bench.backend.benchmark_pipeline import make_benchmark_pipeline
from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.concurrency import CancellationToken, RunDispatcher
from ollama_llm_bench.backend.csv_export import make_table_serializer
from ollama_llm_bench.backend.domain import ProviderId, ProviderType
from ollama_llm_bench.backend.embedding import make_embedding_service
from ollama_llm_bench.backend.errors import (  # fmt: skip
    ConfigurationError,
    ContractViolationError,
    PersistenceError,
)
from ollama_llm_bench.backend.events import (  # fmt: skip
    SIGNAL_APP_SETTINGS_CHANGED,
    AppSettingsChangedEvent,
    EventBus,
)
from ollama_llm_bench.backend.import_export import make_import_export_service
from ollama_llm_bench.backend.infra import (  # fmt: skip
    InstanceLockHandle,
    InstanceLockOutcome,
    acquire_instance_lock,
    make_system_clock,
)
from ollama_llm_bench.backend.log_formatting import make_log_formatter
from ollama_llm_bench.backend.persistence.app_settings import (  # fmt: skip
    DB_FILENAME,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.model_capabilities import create_model_capabilities_store
from ollama_llm_bench.backend.persistence.providers import (  # fmt: skip
    create_providers_store,
    seed_builtin_providers,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.backend.provider_anthropic.api import (  # fmt: skip
    AnthropicClientCollaborators,
    make_anthropic_client,
)
from ollama_llm_bench.backend.provider_gemini.api import (  # fmt: skip
    GeminiClientCollaborators,
    make_gemini_client,
)
from ollama_llm_bench.backend.provider_openai_compatible.api import (  # fmt: skip
    OpenAICompatibleClientCollaborators,
    make_openai_client,
)
from ollama_llm_bench.backend.provider_registry import (  # fmt: skip
    ClientBuilder,
    LLMClient,
    ProviderRegistry,
    make_provider_registry,
)
from ollama_llm_bench.backend.readiness import make_readiness_service
from ollama_llm_bench.backend.run_analysis import make_run_analysis_service
from ollama_llm_bench.backend.run_drift import make_run_drift_detector
from ollama_llm_bench.backend.settings import (  # fmt: skip
    make_run_snapshot_builder,
    make_settings_atomic_writer,
    make_settings_service,
)
from ollama_llm_bench.backend.stores import make_run_registry_store, make_workspace_store
from ollama_llm_bench.backend.stores.inference_activity import make_inference_activity_store
from ollama_llm_bench.backend.task_files import make_task_file_loader, make_task_file_validator
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.common_dialogs import (  # fmt: skip
    AboutDialogCollaborators,
    ErrorDialogPattern,
    ErrorDialogPayload,
    make_about_dialog,
    make_error_dialog,
)
from ollama_llm_bench.ui.main_window import make_main_window, make_status_bar
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.results import ResultCollaborators, make_result_widget
from ollama_llm_bench.ui.resume_benchmark import (  # fmt: skip
    ResumeBenchmarkCollaborators,
    make_resume_benchmark_widget,
)
from ollama_llm_bench.ui.settings_dialog import SettingsDialogCollaborators, make_settings_dialog
from ollama_llm_bench.ui.task_editor import TaskEditorCollaborators, make_task_editor_workspace
from ollama_llm_bench.ui.theme import (  # fmt: skip
    PlatformKind as UiPlatformKind,
    ThemeSetting,
    make_theme_manager,
)

__all__: list[str] = ["AppHandle", "build_app"]

_LOG = structlog.get_logger("app.compose")


class AppHandle(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Composition-root return value (ADR-0010): the shown window and the full 5-step shutdown handle (`shutdown()`) plus the raw resource handles it needs. `shutdown()` performs steps 1-5 of the six-step ordered shutdown (`05_CONCURRENCY_GUARANTEES.md` §8); step 6 (process exit) is `__main__.py`'s responsibility, since it runs only after `app.exec()` itself has returned."""  # fmt: skip

    window: QMainWindow
    write_conn: sqlite3.Connection
    write_lock: threading.Lock
    task_runner: QtTaskRunner[object]
    run_dispatcher: RunDispatcher
    http_client: httpx.Client
    instance_lock: InstanceLockHandle
    loop: QEventLoop
    flow: QtBenchmarkFlow

    def shutdown(self, *, timeout_ms: int) -> None:
        """Run the ordered shutdown's steps 1-5, in order (steps 1-2 first). ``timeout_ms`` bounds the pipeline's hard-cancel/dispatcher-join wait (step 1 and the dispatcher-join half of step 2)."""  # fmt: skip
        self.flow.shutdown(timeout_ms)  # 1: hard-cancel; 2a: join the dispatcher thread
        self.task_runner.shutdown()  # 2b: drain the TaskRunner pool
        self.http_client.close()  # 3
        with self.write_lock:  # 4
            self.write_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.write_conn.close()
        self.instance_lock.release()  # 5


def _abort_launch(
    *, title: str, message: str, detail: str, clipboard: Clipboard, bus: EventBus
) -> NoReturn:
    """Show a FATAL error dialog naming a launch failure, then exit the process.

    Used by every launch-abort path that fires before the object graph is wired
    (ADR-0010) -- no ``AppHandle`` exists yet at that point, so there is nothing
    to shut down beyond the dialog itself.

    Args:
        title: The dialog's title.
        message: The plain-language explanation shown above the detail block.
        detail: The path/file/version detail naming what failed.
        clipboard: Backs the dialog's Copy Details button.
        bus: Backs the dialog's Copy Details toast.
    """
    payload = ErrorDialogPayload(
        title=title,
        message=message,
        detail=detail,
        pattern=ErrorDialogPattern.FATAL,
        quit_callback=_quit_nested_event_loop,
    )
    make_error_dialog(payload=payload, clipboard=clipboard, event_bus=bus).exec()
    sys.exit(1)


def _quit_nested_event_loop() -> None:
    """Stop the abort modal's nested Qt event loop so ``.exec()`` returns -- no ``AppHandle`` exists yet at any ``_abort_launch`` call site, so unlike ``__main__.py``'s crash-hook quit callback there is nothing to ``shutdown()`` first."""  # fmt: skip
    if (instance := QApplication.instance()) is not None:
        instance.exit(1)


def build_app(*, app: QApplication, loop: QEventLoop) -> AppHandle:  # noqa: PLR0915
    """Wire the whole application object graph once, by hand (ADR-0010, ADR-0014)."""
    clipboard = make_clipboard()
    bus = make_qt_event_bus_deliverer()
    clock = make_system_clock()

    detector = make_platform_detector()
    profile = detector.detect()
    plat = UiPlatformKind(profile.kind.value)

    try:
        app_data_root = create_app_data_dir(profile.app_data_root)
    except ConfigurationError as exc:
        _LOG.error("launch_aborted", reason="app_data_permission_denied", detail=str(exc))
        _abort_launch(title="Cannot Create Application Data Folder", message="Ollama LLM Bench could not create its application data folder and cannot start.", detail=str(exc), clipboard=clipboard, bus=bus)  # fmt: skip

    try:
        lock_result = acquire_instance_lock(app_data_root=app_data_root, clock=clock)
    except ConfigurationError as exc:
        _LOG.error("launch_aborted", reason="instance_lock_unavailable", detail=str(exc))
        _abort_launch(title="Cannot Access Instance Lock", message="Ollama LLM Bench could not acquire its instance lock and cannot start.", detail=str(exc), clipboard=clipboard, bus=bus)  # fmt: skip
    if lock_result.outcome is InstanceLockOutcome.ALREADY_RUNNING:
        _LOG.error(
            "launch_aborted", reason="instance_lock_already_running", detail=str(app_data_root)
        )
        _abort_launch(title="Already Running", message="Ollama LLM Bench is already running against this application data folder. Only one copy can run against the same folder at a time.", detail=str(app_data_root), clipboard=clipboard, bus=bus)  # fmt: skip
    instance_lock = lock_result.lock
    if instance_lock is None:
        message = "acquire_instance_lock reported ACQUIRED with no release handle"
        raise ContractViolationError(message=message)

    try:
        write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    except PersistenceError as exc:
        instance_lock.release()
        _LOG.error("launch_aborted", reason="database_unreadable", detail=str(exc))
        _abort_launch(title="Database File Unreadable", message="The application database file exists but could not be opened. It may be corrupt.", detail=f"{app_data_root / DB_FILENAME}\n\n{exc}", clipboard=clipboard, bus=bus)  # fmt: skip

    try:
        ensure_schema(write_conn, lock, clock=clock)
    except PersistenceError as exc:
        write_conn.close()
        instance_lock.release()
        _LOG.error("launch_aborted", reason="schema_version_mismatch", detail=str(exc))
        _abort_launch(title="Incompatible Database", message="The database schema does not match this application version. Remove or relocate the database file so a fresh one can be created.", detail=f"{app_data_root / DB_FILENAME}\n\n{exc}", clipboard=clipboard, bus=bus)  # fmt: skip

    read_conn = functools.partial(open_read_connection, app_data_root / DB_FILENAME)
    runs = create_runs_store(write_conn, lock, read_conn)
    tasks = create_tasks_store(write_conn, lock, read_conn)
    res = create_results_store(write_conn, lock, read_conn)
    res.recover_in_flight_results()
    provs = create_providers_store(write_conn, lock, read_conn)
    caps = create_model_capabilities_store(write_conn, lock, read_conn)
    appset = create_app_settings_store(write_conn, lock, read_conn, clock)

    if not provs.list_providers():
        seed_builtin_providers(write_conn, lock)

    settings = make_settings_service(store=appset, event_bus=bus)
    snapshot_builder = make_run_snapshot_builder(store=appset)
    atomic_writer = make_settings_atomic_writer(write_conn=write_conn, lock=lock, providers_store=provs, app_settings_store=appset)  # fmt: skip
    gate = make_inference_activity_store(clock=clock, event_bus=bus)
    task_runner: QtTaskRunner[object] = make_qt_task_runner()
    dispatcher = make_run_dispatcher()
    http_client = httpx.Client()

    openai_collabs = OpenAICompatibleClientCollaborators(clock=clock, event_bus=bus, inference_activity_store=gate, http_client=http_client)  # fmt: skip
    anthropic_collabs = AnthropicClientCollaborators(clock=clock, event_bus=bus, inference_activity_store=gate, http_client=http_client)  # fmt: skip
    gemini_collabs = GeminiClientCollaborators(clock=clock, event_bus=bus, inference_activity_store=gate, http_client=http_client)  # fmt: skip
    client_builders: Mapping[ProviderType, ClientBuilder] = {
        ProviderType.OPENAI_COMPATIBLE: functools.partial(make_openai_client, collaborators=openai_collabs),
        ProviderType.ANTHROPIC: functools.partial(make_anthropic_client, collaborators=anthropic_collabs),
        ProviderType.GEMINI: functools.partial(make_gemini_client, collaborators=gemini_collabs),
    }  # fmt: skip
    registry: ProviderRegistry = make_provider_registry(providers_store=provs, client_builders=client_builders, gate=gate, event_bus=bus)  # fmt: skip
    embedding_selector = _ReadinessEmbeddingSelector(settings=settings, providers_store=provs)
    readiness = make_readiness_service(registry=registry, embedding_selector=embedding_selector, settings=settings, gate=gate, event_bus=bus, task_runner=task_runner, clock=clock)  # fmt: skip

    # Fix 1: never crash startup over the embedding selection -- degrade to `_NullEmbeddingClient` rather than substitute a provider the user never chose.
    emb_name = settings.get_str("embedding.selected_provider_name")
    emb_model_name = settings.get_str("embedding.selected_model_name")
    emb_provider = provs.get_by_name(emb_name) if emb_name else None
    embedding_client: LLMClient = _NullEmbeddingClient()
    embedding_provider_id: ProviderId = emb_provider.provider_id if emb_provider is not None else ""  # fmt: skip
    if emb_provider is not None and emb_provider.enabled:
        with contextlib.suppress(ConfigurationError):  # env-var may not resolve; degrade
            embedding_client = registry.get_client(emb_provider.provider_id)
    embedding_service = make_embedding_service(client=embedding_client, provider_id=embedding_provider_id, model_name=emb_model_name, snapshot=snapshot_builder.build_snapshot())  # fmt: skip
    pipeline = make_benchmark_pipeline(results_store=res, runs_store=runs, tasks_store=tasks, inference_activity_store=gate, task_runner=task_runner, run_dispatcher=dispatcher, bus=bus, clock=clock, embedding_service=embedding_service, provider_registry=registry, settings_service=settings, run_snapshot_builder=snapshot_builder)  # fmt: skip
    flow = make_qt_benchmark_flow(pipeline=pipeline)

    task_file_loader = make_task_file_loader()
    task_file_validator = make_task_file_validator()
    yaml_formatter = make_yaml_formatter()
    native_pickers = make_native_pickers()
    fsa = make_file_system_actions()
    file_change_watcher = make_file_change_watcher()
    run_analysis = make_run_analysis_service(runs_store=runs, results_store=res, tasks_store=tasks, provider_registry=registry, inference_activity_store=gate, event_bus=bus, clock=clock)  # fmt: skip
    chart = make_chart_aggregator()
    serializer = make_table_serializer()
    drift = make_run_drift_detector()
    import_export = make_import_export_service(providers_store=provs, app_settings_store=appset, event_bus=bus)  # fmt: skip
    run_registry = make_run_registry_store()
    workspace_store = make_workspace_store()

    active_run_task_paths = _NoActiveRunTaskPaths()
    run_validator = _NoRunValidator()
    export_filenames = _ExportFilenameBridge()
    app_version = _resolve_app_version()
    theme_manager = make_theme_manager(app=app, theme_setting=ThemeSetting(settings.get_str("ui.theme") or "system"), platform_kind=plat)  # fmt: skip

    def _reapply_theme_on_settings_change(payload: object) -> None:
        """Re-read `ui.theme` and re-apply it live when a settings write changed it (08-J, 08-D §13)."""
        if isinstance(payload, AppSettingsChangedEvent) and "ui.theme" in payload.changed_keys:
            theme_manager.set_theme_setting(ThemeSetting(settings.get_str("ui.theme") or "system"))

    bus.subscribe(SIGNAL_APP_SETTINGS_CHANGED, _reapply_theme_on_settings_change, owner=theme_manager)  # fmt: skip
    log_formatter = make_log_formatter()

    # Fix 2: one shared status bar built before the window; `parent=status_bar` gives NotificationService's modals a real parent instead of an orphan `QWidget()`.
    status_bar = make_status_bar(theme_manager=theme_manager, platform_kind=plat, app_version=app_version)  # fmt: skip
    notifications = make_notification_service(status_bar=status_bar, parent=status_bar)

    main_window_gateway = make_main_window_gateway(app_settings=appset, settings=settings, readiness=readiness, flow=flow, dispatcher=dispatcher)  # fmt: skip
    new_benchmark_gateway = make_new_benchmark_gateway(app_settings=appset, settings=settings, provider_registry=registry, readiness=readiness, flow=flow, notification=notifications)  # fmt: skip
    progress_gateway = make_progress_gateway(app_settings=appset, settings=settings, flow=flow, runs_store=runs, results_store=res, platform_detector=profile, task_runner=task_runner, clock=clock, probe_command=_NoOpManualProviderProbeCommand(), write_status=_AlwaysOkRunLogWriteStatus())  # fmt: skip
    result_gateway = make_result_gateway(app_settings=appset, settings=settings, runs_store=runs, results_store=res, tasks_store=tasks, run_analysis=run_analysis, gate=gate, provider_registry=registry, chart=chart, serializer=serializer, task_runner=task_runner, clock=clock)  # fmt: skip
    resume_gateway = make_resume_gateway(app_settings=appset, runs_store=runs, results_store=res, tasks_store=tasks, readiness=readiness, providers_store=provs, provider_registry=registry, detector=drift, flow=flow, serializer=serializer, clock=clock)  # fmt: skip
    settings_gateway = make_settings_gateway(providers_store=provs, app_settings_store=appset, model_capabilities_store=caps, settings=settings, atomic_writer=atomic_writer, provider_registry=registry, readiness=readiness, import_export=import_export, gate=gate, task_runner=task_runner, dispatcher=dispatcher, clock=clock)  # fmt: skip
    task_editor_gateway = make_task_editor_gateway(app_settings=appset, settings=settings, workspace_store=workspace_store, run_registry=run_registry, active_run_task_paths=active_run_task_paths)  # fmt: skip

    def _make_benchmark_workspace() -> QWidget:
        # Left panel: New Benchmark + Resume tabs; `objectName` is the stable handle the shell's AC-4 reflow locates this panel by.
        nb_collabs = NewBenchmarkCollaborators(gateway=new_benchmark_gateway, event_bus=bus, task_file_loader=task_file_loader, mode_visibility_policy=mode_visibility, run_validator=run_validator, native_pickers=native_pickers, workspace=workspace_controller, theme_manager=theme_manager, platform_kind=plat)  # fmt: skip
        new_benchmark_widget = make_new_benchmark_widget(collaborators=nb_collabs)
        resume_collabs = ResumeBenchmarkCollaborators(gateway=resume_gateway, event_bus=bus, native_pickers=native_pickers, file_system_actions=fsa, export_filenames=export_filenames, theme_manager=theme_manager, platform_kind=plat)  # fmt: skip
        resume_widget = make_resume_benchmark_widget(collaborators=resume_collabs)
        left_panel = QTabWidget()
        left_panel.setObjectName("benchmark_left_panel")
        left_panel.addTab(new_benchmark_widget, "New Benchmark")
        left_panel.addTab(resume_widget, "Resume")
        progress_widget = make_progress_widget(bus=bus, gateway=progress_gateway, log_formatter=log_formatter)  # fmt: skip
        result_collabs = ResultCollaborators(bus=bus, gateway=result_gateway, native_pickers=native_pickers, clipboard=clipboard, file_system_actions=fsa, notifications=notifications, export_filenames=export_filenames, provider_source=registry, model_fetcher=_NoModelFetcher(), platform_kind=plat)  # fmt: skip
        result_widget = make_result_widget(collaborators=result_collabs)
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        for widget, width in ((left_panel, 360), (progress_widget, 580), (result_widget, 500)):  # fmt: skip
            widget.setMinimumWidth(width)
            splitter.addWidget(widget)
        splitter.setSizes([360, 580, 500])
        return splitter

    def _make_task_editor_workspace() -> QWidget:
        te_collabs = TaskEditorCollaborators(gateway=task_editor_gateway, task_file_loader=task_file_loader, task_file_validator=task_file_validator, yaml_formatter=yaml_formatter, file_change_watcher=file_change_watcher, native_pickers=native_pickers, file_system_actions=fsa, clipboard=clipboard)  # fmt: skip
        return make_task_editor_workspace(bus=bus, collaborators=te_collabs)

    # One QStackedWidget both the WorkspaceController and shell host. Fix 3: the *final* switch_to lands on the persisted `ui.active_workspace` (not hardcoded "benchmark"); the other workspace primes first so both pages get built.
    persisted_workspace = settings.get_str("ui.active_workspace")
    active_workspace = persisted_workspace if persisted_workspace in {"benchmark", "task_editor"} else "benchmark"  # fmt: skip
    priming_workspace = "task_editor" if active_workspace == "benchmark" else "benchmark"
    workspace_region = QStackedWidget()
    workspace_controller = make_workspace_controller(workspace_store=workspace_store, event_bus=bus, container=workspace_region, workspace_factories={"benchmark": _make_benchmark_workspace, "task_editor": _make_task_editor_workspace})  # fmt: skip
    workspace_controller.switch_to(priming_workspace)
    workspace_controller.switch_to(active_workspace)

    def _open_settings() -> None:
        sd_collabs = SettingsDialogCollaborators(gateway=settings_gateway, event_bus=bus, native_pickers=native_pickers, clipboard=clipboard, file_system_actions=fsa, notifications=notifications, theme_manager=theme_manager, platform_kind=plat)  # fmt: skip
        make_settings_dialog(collaborators=sd_collabs, parent=window).exec()

    def _open_about() -> None:
        ab_collabs = AboutDialogCollaborators(clipboard=clipboard, file_system_actions=fsa, event_bus=bus)  # fmt: skip
        make_about_dialog(collaborators=ab_collabs, version=app_version, data_folder_path=str(app_data_root), parent=window).exec()  # fmt: skip

    window = make_main_window(event_bus=bus, gateway=main_window_gateway, workspace=workspace_controller, notifications=notifications, file_system_actions=fsa, container=workspace_region, status_bar=status_bar, app_version=app_version, settings_requested=_open_settings, about_requested=_open_about)  # fmt: skip
    return AppHandle(window=window, write_conn=write_conn, write_lock=lock, task_runner=task_runner, run_dispatcher=dispatcher, http_client=http_client, instance_lock=instance_lock, loop=loop, flow=flow)  # fmt: skip


def _resolve_app_version() -> str:
    try:
        return importlib.metadata.version("ollama-llm-bench")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"
