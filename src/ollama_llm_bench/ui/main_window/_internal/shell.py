"""``MainWindowShell`` -- the ``QMainWindow`` composing the three shell regions (STORY-053).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §2 (window layout),
§2.1 (Benchmark workspace idle/running reflow), §6 (window-level run states).

**Forward-compatibility seam (AC-4).** The real three-panel Benchmark splitter (Run
configuration / Progress / Result) is a later story's job (STORY-054+). This shell proves
only the *reflow mechanism* AC-4 requires -- removing a left-slot control from the layout
when a run starts and restoring it when the run reaches a terminal state -- against a small
stand-in placeholder widget it builds itself, not against ``benchmark_workspace_factory``'s
real content. Once the real Benchmark workspace lands, it is expected to expose a queryable
left-panel child the reflow logic can act on directly; until then, this placeholder keeps
the mechanism demonstrable and testable in isolation.

**Workspace-region container ownership.** This shell owns and exposes
``workspace_region`` -- the ``QStackedWidget`` a later ``compose.py`` story feeds into
``adapters.workspace_controller.make_workspace_controller(..., container=...)`` as the same
container instance. In the meantime this shell also uses ``workspace_region`` itself to host
the two workspace pages it builds from the injected factories, purely so the shell is a
complete, showable widget for this story's own tests; reconciling that with the real
``WorkspaceController``'s ownership of workspace-page mounting is explicitly deferred to the
``compose.py`` story (Phase 11).
"""

from collections.abc import Callable
from typing import override

from PySide6.QtCore import QTimer, Signal as QtSignal
from PySide6.QtGui import QCloseEvent, QMoveEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget
import structlog

from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.ui.main_window._internal.geometry import geometry_to_str
from ollama_llm_bench.ui.main_window._internal.menu_bar import MenuBarWidget
from ollama_llm_bench.ui.main_window._internal.status_bar import StatusBarWidget
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel

__all__: list[str] = ["MainWindowShell"]

logger = structlog.get_logger(__name__)

_MIN_WIDTH = 1280
_MIN_HEIGHT = 720
_LEFT_SLOT_WIDTH = 360


class MainWindowShell(QMainWindow):
    """Composes the menu bar, the workspace region, and the status bar (§2)."""

    geometry_changed = QtSignal(str)

    def __init__(
        self,
        *,
        menu_bar: MenuBarWidget,
        status_bar: StatusBarWidget,
        benchmark_workspace_factory: Callable[[], QWidget],
        task_editor_workspace_factory: Callable[[], QWidget],
        app_version: str,
    ) -> None:
        """Build the shell's fixed three-region layout.

        Args:
            menu_bar: The mounted menu-bar widget.
            status_bar: The mounted status-bar widget.
            benchmark_workspace_factory: Builds the Benchmark workspace page.
            task_editor_workspace_factory: Builds the Task Editor workspace page.
            app_version: Retained for parity with the spec's factory signature; the
                default window title is computed by the controller, not this shell.
        """
        super().__init__()
        self.setObjectName("main_window")
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._app_version = app_version
        self._menu_bar = menu_bar
        self._status_bar = status_bar
        self._task_editor_workspace_factory = task_editor_workspace_factory
        self._on_show_callback: Callable[[], None] | None = None
        self._close_delegate: Callable[[], None] | None = None
        self._has_scheduled_initial_show_tick = False
        self._quitting = False
        self._workspace_region = QStackedWidget()
        self._workspace_region.setObjectName("workspace_region")
        self._left_slot_placeholder = _build_left_slot_placeholder()
        self._benchmark_page = _build_benchmark_page(
            left_slot=self._left_slot_placeholder,
            benchmark_content=benchmark_workspace_factory(),
        )
        self._workspace_region.addWidget(self._benchmark_page)
        self._workspace_pages: dict[str, QWidget] = {"benchmark": self._benchmark_page}
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
        """The ``QStackedWidget`` region a future ``compose.py`` story reuses as the
        real ``WorkspaceController``'s container (see the module docstring)."""
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
        self._left_slot_placeholder.setVisible(not view_model.running_pill_visible)
        self._show_workspace(view_model.active_workspace)

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
        layout.addWidget(self._status_bar)
        self.setCentralWidget(central)

    def _show_workspace(self, name: str) -> None:
        self._workspace_region.setCurrentWidget(self._workspace_page_for(name))

    def _workspace_page_for(self, name: str) -> QWidget:
        if name not in self._workspace_pages:
            if name != "task_editor":
                raise ContractViolationError(
                    message=f"invalid workspace name {name!r}; must be one of "
                    f"{sorted({*self._workspace_pages, 'task_editor'})}"
                )
            page = self._task_editor_workspace_factory()
            self._workspace_region.addWidget(page)
            self._workspace_pages[name] = page
            logger.debug("task_editor_workspace_built_lazily")
        return self._workspace_pages[name]


def _build_left_slot_placeholder() -> QWidget:
    """Build the stand-in left-slot widget the AC-4 reflow mechanism removes/restores."""
    placeholder = QWidget()
    placeholder.setObjectName("benchmark_left_slot_placeholder")
    placeholder.setFixedWidth(_LEFT_SLOT_WIDTH)
    return placeholder


def _build_benchmark_page(*, left_slot: QWidget, benchmark_content: QWidget) -> QWidget:
    """Compose the Benchmark workspace page: the left-slot placeholder plus its content."""
    page = QWidget()
    page.setObjectName("benchmark_workspace_page")
    layout = QHBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(left_slot)
    layout.addWidget(benchmark_content, 1)
    return page
