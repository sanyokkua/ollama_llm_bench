"""Public factory for ``ui/main_window/`` (STORY-053): the application shell.

Source of truth: ``docs/v3_specification/01_Main_Window/description.md``,
``01_Main_Window/state_machine.md``, ``01_Main_Window/implementation_structure.md``,
``08_Cross_Cutting/08-E_interfaces_contracts.md`` §7b.1.

**Resolved, additive deviation from the spec's literal factory signature**
(``01_Main_Window/implementation_structure.md`` §2). The status-bar health dot (08-D §6)
must repaint live on theme change, including the CHECKING-state pulse. Every existing
themed custom-painted widget in this codebase (``ui.shared.make_health_dot``,
``ui.shared.make_badge_label``) requires an explicit ``theme_manager: ThemeManager`` +
``platform_kind: PlatformKind`` pair with no global/singleton accessor -- the spec's
literal ``make_main_window(...)`` signature has neither parameter, a genuine spec silence.
Per this narrow, justified, additive decision, ``make_main_window`` gains two extra
required keyword-only parameters, ``theme_manager`` and ``platform_kind``; ``compose.py``
(a later Phase-11 story) passes the same ``ThemeManager`` instance it constructs once at
startup.
"""

from collections.abc import Callable

import icontract
from PySide6.QtWidgets import QMainWindow, QWidget

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.main_window._internal.close_handler import CloseHandler
from ollama_llm_bench.ui.main_window._internal.controller import MainWindowController
from ollama_llm_bench.ui.main_window._internal.geometry import (
    DebouncedGeometryWriter,
    restore_geometry,
)
from ollama_llm_bench.ui.main_window._internal.menu_bar import MenuBarWidget
from ollama_llm_bench.ui.main_window._internal.shell import MainWindowShell
from ollama_llm_bench.ui.main_window._internal.status_bar import StatusBarWidget
from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["make_main_window"]


@icontract.require(lambda app_version: len(app_version) > 0, "app_version must be non-empty")
@icontract.require(
    lambda benchmark_workspace_factory, task_editor_workspace_factory: (
        benchmark_workspace_factory is not None and task_editor_workspace_factory is not None
    ),
    "both workspace factories are required collaborators wired by compose.py",
)
@icontract.ensure(lambda result: isinstance(result, QMainWindow))
def make_main_window(  # noqa: PLR0913  # ten distinct required collaborators per the
    # approved STORY-053 design (docs/stories/story-053-main-window-shell.md); this is the
    # module's sole public factory and every parameter is a compose.py-wired collaborator
    *,
    event_bus: EventBus,
    gateway: MainWindowGateway,
    workspace: WorkspaceController,
    notifications: NotificationService,
    file_system_actions: FileSystemActions,
    benchmark_workspace_factory: Callable[[], QWidget],
    task_editor_workspace_factory: Callable[[], QWidget],
    app_version: str,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> QMainWindow:
    """Construct the application shell.

    Builds the menu bar, the swappable workspace region, and the status bar, wires the
    ``MainWindowController`` to the Event Bus, restores the persisted window geometry
    before the window is shown, and returns the top-level ``QMainWindow``.

    Args:
        event_bus: The bus the controller subscribes the ten shell events on.
        gateway: The adapter gateway exposing the shell's settings/readiness/run-activity
            query and command surface (D-R-06).
        workspace: Reads and switches the active workspace.
        notifications: Surfaces toasts for the blocked-health-dot-click case.
        file_system_actions: Retained for the "open in file manager" affordance a later
            story exposes from this shell.
        benchmark_workspace_factory: Builds the Benchmark workspace widget.
        task_editor_workspace_factory: Builds the Task Editor workspace widget.
        app_version: The application version string shown in the menu bar, the status
            bar, and the default window title.
        theme_manager: The live theme switcher the status-bar health dot re-reads its
            colour role from on every theme change (see the module docstring).
        platform_kind: The host platform classification the health dot resolves
            alongside ``theme_manager``.

    Returns:
        The fully wired top-level ``QMainWindow``, ready to be shown.
    """
    menu_bar = MenuBarWidget(app_version=app_version)
    status_bar = StatusBarWidget(
        theme_manager=theme_manager, platform_kind=platform_kind, app_version=app_version
    )
    shell = MainWindowShell(
        menu_bar=menu_bar,
        status_bar=status_bar,
        benchmark_workspace_factory=benchmark_workspace_factory,
        task_editor_workspace_factory=task_editor_workspace_factory,
        app_version=app_version,
    )
    geometry_writer = DebouncedGeometryWriter(gateway=gateway)
    shell.geometry_changed.connect(geometry_writer.on_window_geometry_changed)

    def _on_confirmed_quit() -> None:
        geometry_writer.flush()
        shell.force_close()

    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        on_confirmed_quit=_on_confirmed_quit,
    )
    controller = MainWindowController(
        gateway=gateway,
        event_bus=event_bus,
        workspace=workspace,
        notifications=notifications,
        file_system_actions=file_system_actions,
        shell=shell,
        close_handler=close_handler,
        app_version=app_version,
    )
    controller.bind()
    restore_geometry(shell, gateway)
    return shell
