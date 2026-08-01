"""``MainWindowShell`` -- the ``QMainWindow`` composing the three shell regions (STORY-053,
STORY-077).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §2 (window layout),
§2.1 (Benchmark workspace idle/running reflow), §6 (window-level run states).

**Single-container ownership (STORY-077).** This shell hosts the one ``QStackedWidget`` the
real ``WorkspaceController`` (``adapters/workspace_controller/``) owns and switches pages
on -- ``compose.py`` constructs that ``QStackedWidget`` once, hands it to
``make_workspace_controller(..., container=...)``, primes both workspace pages into it, and
passes the *same instance* into this shell as ``workspace_region``. This shell never builds a
workspace page itself and never switches the container's current widget -- that is
``WorkspaceController.switch_to(...)``'s job alone, so there is exactly one set of workspace
widget instances and exactly one place that changes what is on screen.

**AC-4 reflow mechanism.** The Benchmark workspace's left run-configuration panel (New
Benchmark/Resume tabs) is a queryable child of the container, located by the stable
``objectName`` ``"benchmark_left_panel"`` that ``compose.py``'s Benchmark-workspace composite
sets on it. ``apply_view_model`` toggles that panel's visibility directly -- hiding a
``QWidget`` inside a ``QBoxLayout`` removes it from the visible layout entirely (Qt's default
layout behaviour), matching the running layout's "left panel removed from the layout" rule
(`01_Main_Window/description.md` §2.1) with no explicit ``layout.removeWidget`` call needed.
"""

from collections.abc import Callable
from typing import Final, cast, override

from PySide6.QtCore import QTimer, Signal as QtSignal
from PySide6.QtGui import QCloseEvent, QMoveEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget
import structlog

from ollama_llm_bench.ui.main_window._internal.geometry import geometry_to_str
from ollama_llm_bench.ui.main_window._internal.menu_bar import MenuBarWidget
from ollama_llm_bench.ui.main_window._internal.status_bar import StatusBarWidget
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel

__all__: list[str] = ["MainWindowShell"]

logger = structlog.get_logger(__name__)

_MIN_WIDTH = 1280
_MIN_HEIGHT = 720
_LEFT_PANEL_OBJECT_NAME: Final[str] = "benchmark_left_panel"


class MainWindowShell(QMainWindow):
    """Composes the menu bar, the workspace region, and the status bar (§2)."""

    geometry_changed = QtSignal(str)

    def __init__(
        self,
        *,
        menu_bar: MenuBarWidget,
        status_bar: StatusBarWidget,
        workspace_region: QStackedWidget,
        app_version: str,
    ) -> None:
        """Build the shell's fixed three-region layout.

        Args:
            menu_bar: The mounted menu-bar widget.
            status_bar: The mounted status-bar widget.
            workspace_region: The ``QStackedWidget`` the real ``WorkspaceController`` owns
                and switches pages on (see the module docstring); this shell only hosts it.
            app_version: Retained for parity with the spec's factory signature; the
                default window title is computed by the controller, not this shell.
        """
        super().__init__()
        self.setObjectName("main_window")
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._app_version = app_version
        self._menu_bar = menu_bar
        self._status_bar = status_bar
        self._on_show_callback: Callable[[], None] | None = None
        self._close_delegate: Callable[[], None] | None = None
        self._has_scheduled_initial_show_tick = False
        self._quitting = False
        self._workspace_region = workspace_region
        self._workspace_region.setObjectName("workspace_region")
        self._build_layout()

    @property
    def menu_bar(self) -> MenuBarWidget:
        """The mounted menu-bar widget, for controller signal wiring."""
        return self._menu_bar

    @property
    def status_bar(self) -> StatusBarWidget:
        """The mounted status-bar widget, for controller signal wiring."""
        return self._status_bar

    @property
    def workspace_region(self) -> QStackedWidget:
        """The ``QStackedWidget`` region the real ``WorkspaceController`` switches pages on."""
        return self._workspace_region

    def set_on_show_callback(self, callback: Callable[[], None]) -> None:
        """Register the callback the deferred readiness-probe tick invokes on first show."""
        self._on_show_callback = callback

    def set_close_delegate(self, delegate: Callable[[], None]) -> None:
        """Register the callback a close (X) request is delegated to (the close handler)."""
        self._close_delegate = delegate

    def force_close(self) -> None:
        """Bypass the close-confirmation delegate and actually close the window.

        Called only by the close handler once the quit sequence has fully resolved toward
        quitting -- never by a top-level close (X) request, which always routes through
        ``closeEvent`` to the delegate instead.
        """
        self._quitting = True
        self.close()

    def apply_view_model(self, view_model: MainWindowViewModel) -> None:
        """Reflect ``view_model`` across the whole shell (title, regions, layout reflow).

        Named ``apply_view_model`` rather than ``render`` -- ``QWidget``/``QMainWindow``
        already declare an incompatible ``render(...)`` method (offscreen painting).
        """
        self.setWindowTitle(view_model.window_title)
        self._menu_bar.apply_view_model(view_model)
        self._status_bar.apply_view_model(view_model)
        self._reflow_left_panel(running=view_model.running_pill_visible)

    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._has_scheduled_initial_show_tick or self._on_show_callback is None:
            return
        self._has_scheduled_initial_show_tick = True
        QTimer.singleShot(0, self._on_show_callback)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        if self._close_delegate is not None:
            self._close_delegate()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.geometry_changed.emit(geometry_to_str(self.geometry()))

    @override
    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self.geometry_changed.emit(geometry_to_str(self.geometry()))

    def _build_layout(self) -> None:
        central = QWidget()
        central.setObjectName("main_window_central")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._menu_bar)
        layout.addWidget(self._workspace_region, 1)
        self.setCentralWidget(central)
        # The real QMainWindow status-bar dock area (STORY-077 Fix 2) -- not a fourth
        # region added to the central layout. This is the application's one status-bar
        # object; see `_internal/status_bar.py`'s module docstring.
        self.setStatusBar(self._status_bar)

    def _reflow_left_panel(self, *, running: bool) -> None:
        """Hide/show the Benchmark workspace's left run-configuration panel (§2.1).

        Locates the panel by its stable ``objectName`` so this shell acts on the real New
        Benchmark/Resume tab widget ``compose.py`` builds, not a disconnected placeholder.
        A no-op when the panel is not present (e.g. a test hosting a bare workspace region)
        -- this method never raises on an unpopulated container.
        """
        left_panel = cast("QWidget | None", self._workspace_region.findChild(QWidget, _LEFT_PANEL_OBJECT_NAME))  # fmt: skip
        if left_panel is not None:
            left_panel.setVisible(not running)
