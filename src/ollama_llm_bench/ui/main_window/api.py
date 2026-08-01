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

**``make_status_bar`` (STORY-077 Fix 2) -- a second public factory, added deliberately.**
``compose.py`` must hand the *same* ``StatusBarWidget``/``QStatusBar`` instance to both
``adapters.notification_service.make_notification_service`` and this module's shell, and
must do so *before* ``make_main_window`` is called (``make_main_window`` requires an
already-constructed ``NotificationService``, which itself requires the status bar) --  so
the status bar cannot be built inside ``make_main_window`` any more. ``make_status_bar``
exposes the one construction step ``compose.py`` needs, without reaching into this
module's private ``_internal/`` package (forbidden by import-linter). ``make_main_window``
now takes the pre-built ``status_bar`` as a required parameter instead of the
``theme_manager``/``platform_kind`` pair (needed only to build the status bar, which no
longer happens here).
"""

from collections.abc import Callable

import icontract
from PySide6.QtWidgets import QMainWindow, QStackedWidget

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

__all__: list[str] = ["make_main_window", "make_status_bar"]


@icontract.require(lambda app_version: len(app_version) > 0, "app_version must be non-empty")
def make_status_bar(
    *, theme_manager: ThemeManager, platform_kind: PlatformKind, app_version: str
) -> StatusBarWidget:
    """Construct the Main Window's one status bar (health dot, toast region, version, §4).

    Built *before* ``make_main_window`` so ``compose.py`` can hand this same instance to
    both ``make_main_window`` and ``adapters.notification_service.make_notification_service``
    -- the application has exactly one status-bar object (STORY-077 Fix 2).

    Args:
        theme_manager: The live theme switcher the health dot re-reads its colour role
            from on every theme change.
        platform_kind: The host platform classification the health dot resolves alongside
            ``theme_manager``.
        app_version: The version string shown in the trailing version label.

    Returns:
        A real ``QStatusBar`` subclass, not yet mounted on any window.
    """
    return StatusBarWidget(
        theme_manager=theme_manager, platform_kind=platform_kind, app_version=app_version
    )


@icontract.require(lambda app_version: len(app_version) > 0, "app_version must be non-empty")
@icontract.require(
    lambda container: container is not None,
    "container is the WorkspaceController-owned QStackedWidget wired by compose.py",
)
@icontract.require(
    lambda status_bar: status_bar is not None,
    "status_bar is the pre-built StatusBarWidget wired by compose.py (STORY-077 Fix 2)",
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
    container: QStackedWidget,
    status_bar: StatusBarWidget,
    app_version: str,
    settings_requested: Callable[[], None] | None = None,
    about_requested: Callable[[], None] | None = None,
) -> QMainWindow:
    """Construct the application shell.

    Builds the menu bar, hosts the given workspace region and the pre-built status bar,
    wires the ``MainWindowController`` to the Event Bus, restores the persisted window
    geometry before the window is shown, and returns the top-level ``QMainWindow``.

    Args:
        event_bus: The bus the controller subscribes the ten shell events on.
        gateway: The adapter gateway exposing the shell's settings/readiness/run-activity
            query and command surface (D-R-06).
        workspace: Reads and switches the active workspace; the *same* ``container`` this
            factory receives is the ``QStackedWidget`` this ``WorkspaceController`` was
            constructed with and switches pages on (STORY-077) -- there is exactly one
            container and exactly one set of workspace-page widget instances.
        notifications: Surfaces toasts for the blocked-health-dot-click case; built by
            ``compose.py`` over the *same* ``status_bar`` instance this factory receives
            (STORY-077 Fix 2) -- the application has exactly one status-bar object.
        file_system_actions: Retained for the "open in file manager" affordance a later
            story exposes from this shell.
        container: The ``QStackedWidget`` the real ``WorkspaceController`` owns and
            switches pages on; this shell only hosts it, it never builds or switches a
            workspace page itself.
        status_bar: The pre-built status bar (``make_status_bar``) this shell mounts via
            ``QMainWindow.setStatusBar`` -- built by the caller, before this factory is
            called, so the same instance can also be handed to
            ``adapters.notification_service.make_notification_service``.
        app_version: The application version string shown in the menu bar and the
            default window title.
        settings_requested: Optional callback invoked when the Settings menu-bar action
            is activated (STORY-077); forwarded unchanged to
            ``MainWindowController``, which already declares and defaults this
            parameter.
        about_requested: Optional callback invoked when the About menu-bar action is
            activated (STORY-077); forwarded unchanged to ``MainWindowController``,
            which already declares and defaults this parameter.

    Returns:
        The fully wired top-level ``QMainWindow``, ready to be shown.
    """
    menu_bar = MenuBarWidget(app_version=app_version)
    shell = MainWindowShell(
        menu_bar=menu_bar,
        status_bar=status_bar,
        workspace_region=container,
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
        settings_requested=settings_requested,
        about_requested=about_requested,
    )
    controller.bind()
    restore_geometry(shell, gateway)
    return shell
