"""``MainWindowController`` -- derives the shell view-model from the EventBus (STORY-053).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §9-10 and
``01_Main_Window/implementation_structure.md`` §5. Subscribes to the ten events of §10,
each owner-bound to itself so every subscription auto-cancels when the controller is
destroyed (`08-J_event_bus_catalog.md` §2). Depends only on its own ``MainWindowGateway``
Protocol plus ``EventBus``, ``WorkspaceController``, ``NotificationService``, and
``FileSystemActions`` -- never on a backend Protocol (D-R-06): this module imports no
``backend.settings``, ``backend.readiness``, or ``backend.benchmark_pipeline`` symbol.
"""

from collections.abc import Callable, Sequence
from typing import Final, cast

from PySide6.QtCore import QTimer
import structlog

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController, WorkspaceHint
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderHealth,
    ReadinessState,
    RunId,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    SIGNAL_GLOBAL_MESSAGE,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_PAUSED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_RESUMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_WORKSPACE_CHANGED,
    AppReadinessChangedEvent,
    EventBus,
    GlobalMessageEvent,
    ProviderHealthSummary,
    RunFailedEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunRenamedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStoppedEvent,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.ui.main_window._internal.close_handler import CloseHandler
from ollama_llm_bench.ui.main_window._internal.shell import MainWindowShell
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel
from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway

__all__: list[str] = ["MainWindowController"]

logger = structlog.get_logger(__name__)

_TOAST_CLEAR_MS = 5000
_DISABLED_TOOLTIP = "Disabled - a benchmark is in progress."
_DEFAULT_TITLE_TEMPLATE = "Ollama LLM Bench v{version}"
_RUNNING_TITLE_TEMPLATE = "Ollama LLM Bench - Running: {run_name}"
_PAUSED_TITLE_TEMPLATE = "Ollama LLM Bench - Paused: {run_name}"
_NOT_READY_MODAL_TITLE: Final[str] = "No provider is reachable."
_NOT_READY_MODAL_REMEDY: Final[str] = (
    "Open Settings to check each provider's base URL and credentials, then re-run "
    "the check from the health dot in the status bar."
)

_RunTerminalEvent = RunStoppedEvent | RunFinishedEvent | RunFailedEvent


class MainWindowController:
    """Owns the Main Window's shell state: subscribes, derives, applies."""

    def __init__(  # noqa: PLR0913  # seven distinct required collaborators per the approved
        # STORY-053 design (docs/stories/story-053-main-window-shell.md §5); each is an
        # independently-faked test seam, not groupable into one struct without losing that
        self,
        *,
        gateway: MainWindowGateway,
        event_bus: EventBus,
        workspace: WorkspaceController,
        notifications: NotificationService,
        file_system_actions: FileSystemActions,
        shell: MainWindowShell,
        close_handler: CloseHandler,
        app_version: str,
        settings_requested: Callable[[], None] | None = None,
        about_requested: Callable[[], None] | None = None,
    ) -> None:
        """Store the collaborators and seed the initial shell state.

        Args:
            gateway: The adapter gateway this controller reads/writes shell state
                through (D-R-06).
            event_bus: The bus this controller subscribes the ten shell events on.
            workspace: Reads and switches the active workspace.
            notifications: Surfaces the blocked-health-dot-click toast.
            file_system_actions: Retained for a later story's "open in file manager"
                affordance; unused by this controller directly.
            shell: The shell widget this controller renders the derived view-model into.
            close_handler: The quit sequence this controller delegates window closes to.
            app_version: The version string embedded in the default window title.
            settings_requested: Optional callback for the Settings menu-bar action; the
                Settings dialog itself is a later story's scope.
            about_requested: Optional callback for the About menu-bar action; the About
                dialog itself is a later story's scope.
        """
        self._gateway = gateway
        self._event_bus = event_bus
        self._workspace = workspace
        self._notifications = notifications
        self._file_system_actions = file_system_actions
        self._shell = shell
        self._close_handler = close_handler
        self._app_version = app_version
        self._settings_requested_callback = settings_requested
        self._about_requested_callback = about_requested
        self._current_run_id: RunId | None = None
        self._current_run_name: str | None = None
        self._run_non_terminal = False
        self._is_paused = False
        self._toast_text = ""
        self._active_workspace = gateway.get_active_workspace() or "benchmark"
        snapshot = gateway.readiness_snapshot()
        self._health_state = snapshot.overall
        self._health_tooltip = _format_health_tooltip(snapshot)
        self._toast_clear_timer = QTimer()
        self._toast_clear_timer.setSingleShot(True)
        self._toast_clear_timer.timeout.connect(self._clear_toast)

    def bind(self) -> None:
        """Subscribe to the EventBus, wire shell signals, and render the initial state."""
        self._subscribe_to_events()
        self._shell.set_on_show_callback(self._on_shell_shown)
        self._shell.set_close_delegate(self._close_handler.request_close)
        self._shell.menu_bar.settings_requested.connect(self._on_settings_requested)
        self._shell.menu_bar.about_requested.connect(self._on_about_requested)
        self._shell.menu_bar.workspace_switch_requested.connect(self._on_workspace_switch_requested)
        self._shell.menu_bar.running_pill_clicked.connect(self._on_running_pill_clicked)
        self._shell.status_bar.health_dot_clicked.connect(self._on_health_dot_clicked)
        logger.debug("main_window_controller_constructed", app_version=self._app_version)
        self._render()

    def _subscribe_to_events(self) -> None:
        bus = self._event_bus
        bus.subscribe(
            SIGNAL_RUN_STARTED,
            lambda payload: self._on_run_started(cast("RunStartedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_PAUSED,
            lambda payload: self._on_run_paused(cast("RunPausedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_RESUMED,
            lambda payload: self._on_run_resumed(cast("RunResumedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_STOPPED,
            lambda payload: self._on_run_terminal(cast("RunStoppedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_FINISHED,
            lambda payload: self._on_run_terminal(cast("RunFinishedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_FAILED,
            lambda payload: self._on_run_terminal(cast("RunFailedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_RUN_RENAMED,
            lambda payload: self._on_run_renamed(cast("RunRenamedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_APP_READINESS_CHANGED,
            lambda payload: self._on_readiness_changed(cast("AppReadinessChangedEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_GLOBAL_MESSAGE,
            lambda payload: self._on_global_message(cast("GlobalMessageEvent", payload)),
            owner=self,
        )
        bus.subscribe(
            SIGNAL_WORKSPACE_CHANGED,
            lambda payload: self._on_workspace_changed(cast("WorkspaceChangedEvent", payload)),
            owner=self,
        )

    def _on_shell_shown(self) -> None:
        logger.debug("main_window_shown_readiness_probe_scheduled")
        self._gateway.reprobe()

    def _on_run_started(self, event: RunStartedEvent) -> None:
        self._current_run_id = event.run_id
        self._current_run_name = event.run_name
        self._run_non_terminal = True
        self._is_paused = False
        logger.debug("run_started_reflected", run_id=event.run_id)
        self._render()

    def _on_run_paused(self, event: RunPausedEvent) -> None:
        self._is_paused = True
        logger.debug("run_paused_reflected", run_id=event.run_id)
        self._render()

    def _on_run_resumed(self, event: RunResumedEvent) -> None:
        self._is_paused = False
        logger.debug("run_resumed_reflected", run_id=event.run_id)
        self._render()

    def _on_run_terminal(self, event: _RunTerminalEvent) -> None:
        self._run_non_terminal = False
        self._is_paused = False
        logger.debug("run_terminal_reflected", run_id=event.run_id)
        self._render()

    def _on_run_renamed(self, event: RunRenamedEvent) -> None:
        if self._current_run_id != event.run_id:
            return
        self._current_run_name = event.new_name
        logger.debug("run_renamed_reflected", run_id=event.run_id, new_name=event.new_name)
        self._render()

    def _on_readiness_changed(self, event: AppReadinessChangedEvent) -> None:
        was_not_ready = self._health_state is ReadinessState.NOT_READY
        self._health_state = event.overall
        self._health_tooltip = _format_health_tooltip(event)
        logger.debug("readiness_changed_reflected", overall=event.overall.value)
        # Render before the blocking modal so the status-bar health dot reflects NOT_READY
        # immediately -- `show_error(..., blocking=True)` blocks the GUI thread inside a
        # nested `QMessageBox.critical(...).exec()` loop until the user dismisses it, so a
        # `_render()` placed after that call would leave the status bar showing the
        # previous state for as long as the modal is up. The spec requires the failure be
        # surfaced concurrently in both places (`08_Cross_Cutting/08-M_app_lifecycle.md`
        # §5: "surfaced twice: in the status bar, and through an explanatory modal dialog").
        self._render()
        if event.overall is ReadinessState.NOT_READY and not was_not_ready:
            logger.info("readiness_not_ready_modal_shown")
            self._notifications.show_error(_format_not_ready_modal_text(event), blocking=True)

    def _on_global_message(self, event: GlobalMessageEvent) -> None:
        self._toast_text = event.text
        logger.debug("global_message_shown", severity=event.severity)
        self._render()
        self._toast_clear_timer.stop()
        self._toast_clear_timer.start(_TOAST_CLEAR_MS)

    def _clear_toast(self) -> None:
        self._toast_text = ""
        self._render()

    def _on_workspace_changed(self, event: WorkspaceChangedEvent) -> None:
        if self._shell.is_quitting:
            # Event Bus delivery is queued, so a switch made in the same event-loop
            # turn as the quit can still drain after the confirmed-quit path closed
            # the window -- by which point the ordered shutdown may have closed the
            # write connection, and persisting would raise on it. Nothing is lost:
            # the confirmed-quit path already flushed this setting (api.py).
            logger.debug("workspace_changed_ignored_while_quitting", workspace=event.workspace)
            return
        self._active_workspace = event.workspace
        # §6 requires the write on *every* switch, so the setting survives a crash
        # or a kill -- the quit-time write in api.py is an idempotent flush, not the
        # only one. QtWorkspaceController.switch_to short-circuits a same-workspace
        # call before emitting, so this fires exactly once per real change.
        self._gateway.set_active_workspace(event.workspace)
        logger.debug("workspace_changed_reflected", workspace=event.workspace)
        self._render()

    def _on_settings_requested(self) -> None:
        logger.debug("settings_requested")
        if self._settings_requested_callback is not None:
            self._settings_requested_callback()

    def _on_about_requested(self) -> None:
        logger.debug("about_requested")
        if self._about_requested_callback is not None:
            self._about_requested_callback()

    def _on_workspace_switch_requested(self, name: str) -> None:
        logger.debug("workspace_switch_requested", workspace=name)
        self._workspace.switch_to(name)

    def _on_running_pill_clicked(self) -> None:
        logger.debug("running_pill_clicked")
        self._workspace.switch_to("benchmark", hint=WorkspaceHint(focus_widget="progress"))

    def _on_health_dot_clicked(self) -> None:
        if self._run_non_terminal:
            logger.debug("health_dot_click_blocked")
            self._notifications.show_info(_DISABLED_TOOLTIP)
            return
        logger.debug("health_dot_clicked_reprobe")
        self._gateway.reprobe()

    def _render(self) -> None:
        self._shell.apply_view_model(self._build_view_model())

    def _build_view_model(self) -> MainWindowViewModel:
        return MainWindowViewModel(
            window_title=self._resolve_title(),
            active_workspace=self._active_workspace,
            settings_action_enabled=not self._run_non_terminal,
            running_pill_visible=self._run_non_terminal,
            running_pill_label=self._resolve_run_label(),
            health_state=self._health_state,
            health_tooltip=self._health_tooltip,
            health_dot_clickable=not self._run_non_terminal,
            toast_text=self._toast_text,
        )

    def _resolve_title(self) -> str:
        if not self._run_non_terminal or self._current_run_name is None:
            return _DEFAULT_TITLE_TEMPLATE.format(version=self._app_version)
        template = _PAUSED_TITLE_TEMPLATE if self._is_paused else _RUNNING_TITLE_TEMPLATE
        return template.format(run_name=self._current_run_name)

    def _resolve_run_label(self) -> str:
        if not self._run_non_terminal or self._current_run_name is None:
            return ""
        return self._current_run_name


def _format_health_tooltip(
    snapshot: AppReadinessSnapshot | AppReadinessChangedEvent,
) -> str:
    """Format the per-provider + embedding readiness detail for the health-dot tooltip."""
    return _format_health_lines(
        per_provider=snapshot.per_provider, embedding_reachable=snapshot.embedding_reachable
    )


def _format_not_ready_modal_text(event: AppReadinessChangedEvent) -> str:
    """Explain a totally-failed readiness probe and how to correct it (STORY-081-AC-2).

    Args:
        event: The readiness result whose overall state is ``NOT_READY``.

    Returns:
        A multi-line message naming each unreachable provider, the embedding
        model's reachability, and the remedy.
    """
    unreachable = ", ".join(
        health.provider_id for health in event.per_provider if not health.reachable
    )
    lines = [_NOT_READY_MODAL_TITLE, ""]
    if unreachable:
        lines.append(f"Unreachable providers: {unreachable}")
    if not event.embedding_reachable:
        lines.append("Embedding model: unreachable")
    lines.extend(["", _NOT_READY_MODAL_REMEDY])
    return "\n".join(lines)


def _format_health_lines(
    *,
    per_provider: Sequence[ProviderHealth] | Sequence[ProviderHealthSummary],
    embedding_reachable: bool,
) -> str:
    """Render one ``"provider_id: reachable/unreachable"`` line per provider plus embedding.

    ``per_provider`` accepts either readiness-record shape -- ``ProviderHealth``
    (``AppReadinessSnapshot``) or ``ProviderHealthSummary``
    (``AppReadinessChangedEvent``) -- since both carry the same ``provider_id``/
    ``reachable`` pair this formatter reads.
    """
    lines = [
        f"{item.provider_id}: {'reachable' if item.reachable else 'unreachable'}"
        for item in per_provider
    ]
    lines.append(f"embedding: {'reachable' if embedding_reachable else 'unreachable'}")
    return "\n".join(lines)
