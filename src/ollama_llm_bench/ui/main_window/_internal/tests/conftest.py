"""Shared fixtures for ``ui/main_window/_internal/tests/`` (STORY-053).

Provides an in-process synchronous ``EventBus`` test double (delivers immediately on the
calling call stack, unlike the real Qt-queued ``adapters.qt_event_bus`` implementation, so
controller tests can assert derived state right after ``emit`` with no event-loop pump), an
in-memory ``MainWindowGateway`` test double, and thin fakes for the remaining collaborators
(``WorkspaceController``, ``FileSystemActions``) per the ``testing-standard-pyqt`` mocking
discipline.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from PySide6.QtWidgets import QApplication, QWidget
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint
from ollama_llm_bench.backend.domain import AppReadinessSnapshot, ReadinessState
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.ui.main_window._internal.close_handler import CloseHandler
from ollama_llm_bench.ui.main_window._internal.controller import MainWindowController
from ollama_llm_bench.ui.main_window._internal.menu_bar import MenuBarWidget
from ollama_llm_bench.ui.main_window._internal.shell import MainWindowShell
from ollama_llm_bench.ui.main_window._internal.status_bar import StatusBarWidget
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, ThemeSetting, make_theme_manager

_APP_VERSION = "9.9.9"


class _FakeSubscription:
    """``Subscription`` handle returned by ``FakeEventBus.subscribe``."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double.

    ``emit`` invokes every live subscriber immediately, on the caller's own call stack --
    deliberately unlike the real ``adapters.qt_event_bus`` implementation's queued Qt-signal
    delivery -- so a controller test can assert the derived state right after ``emit`` with no
    event-loop pump required.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            handlers = self._handlers.get(signal_name)
            if handlers is not None and handler in handlers:
                handlers.remove(handler)

        return _FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class FakeMainWindowGateway:
    """An in-memory ``MainWindowGateway`` test double (structural, no ``spec=`` needed)."""

    def __init__(self) -> None:
        self._window_geometry: str | None = None
        self._splitter_sizes: str | None = None
        self._active_workspace: str | None = None
        self._theme = "system"
        self._readiness = AppReadinessSnapshot(
            overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
        )
        self._is_run_active = False
        self.set_window_geometry_calls: list[str] = []
        self.set_splitter_sizes_calls: list[str] = []
        self.shutdown_calls: list[int] = []
        self.reprobe_calls = 0

    def get_window_geometry(self) -> str | None:
        return self._window_geometry

    def set_window_geometry(self, value: str) -> None:
        self._window_geometry = value
        self.set_window_geometry_calls.append(value)

    def get_splitter_sizes(self) -> str | None:
        return self._splitter_sizes

    def set_splitter_sizes(self, value: str) -> None:
        self._splitter_sizes = value
        self.set_splitter_sizes_calls.append(value)

    def get_active_workspace(self) -> str | None:
        return self._active_workspace

    def set_active_workspace(self, value: str) -> None:
        self._active_workspace = value

    def get_theme(self) -> str:
        return self._theme

    def set_theme(self, value: str) -> None:
        self._theme = value

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def set_readiness_snapshot(self, snapshot: AppReadinessSnapshot) -> None:
        self._readiness = snapshot

    def reprobe(self) -> None:
        self.reprobe_calls += 1

    def is_run_active(self) -> bool:
        return self._is_run_active

    def set_run_active(self, value: bool) -> None:  # noqa: FBT001  # test-double setter
        self._is_run_active = value

    def shutdown(self, timeout_ms: int) -> None:
        self.shutdown_calls.append(timeout_ms)


class FakeWorkspaceController:
    """An in-memory ``WorkspaceController`` test double."""

    def __init__(self) -> None:
        self._active = "benchmark"
        self.switch_calls: list[tuple[str, WorkspaceHint | None]] = []

    def active(self) -> str:
        return self._active

    def switch_to(self, name: str, hint: WorkspaceHint | None = None) -> None:
        self._active = name
        self.switch_calls.append((name, hint))


@pytest.fixture
def gateway() -> FakeMainWindowGateway:
    return FakeMainWindowGateway()


@pytest.fixture
def event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def workspace() -> FakeWorkspaceController:
    return FakeWorkspaceController()


@pytest.fixture
def notifications() -> FakeNotificationService:
    return FakeNotificationService()


@pytest.fixture
def file_system_actions(mocker: MockerFixture) -> FileSystemActions:
    return cast("FileSystemActions", mocker.Mock(spec=FileSystemActions))


@pytest.fixture
def platform_kind() -> PlatformKind:
    return PlatformKind.LINUX


@pytest.fixture
def theme_manager(qapp: QApplication, platform_kind: PlatformKind) -> ThemeManager:
    return make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=platform_kind
    )


@dataclass
class MainWindowHarness:
    """A fully wired shell + controller + close handler, for controller-level tests."""

    controller: MainWindowController
    shell: MainWindowShell
    close_handler: CloseHandler
    gateway: FakeMainWindowGateway
    event_bus: FakeEventBus
    workspace: FakeWorkspaceController
    notifications: FakeNotificationService
    app_version: str = _APP_VERSION
    settings_requested_calls: list[None] = field(default_factory=list)
    about_requested_calls: list[None] = field(default_factory=list)


@pytest.fixture
def make_harness(  # noqa: PLR0913  # a pytest fixture composing eight independently
    # overridable per-test fixtures; grouping them into a struct would defeat pytest's own
    # fixture-injection/override mechanism for the individual collaborators
    qtbot: object,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    workspace: FakeWorkspaceController,
    notifications: FakeNotificationService,
    file_system_actions: FileSystemActions,
) -> Callable[..., MainWindowHarness]:
    """Return a factory building a bound ``MainWindowController`` + real ``MainWindowShell``.

    Every collaborator is a fake/test-double from this module's fixtures except the shell,
    menu bar, and status bar, which are the real widgets under test (a widget is never
    replaced by a mock).
    """

    def _make(*, shutdown_timeout_ms: int = 5000) -> MainWindowHarness:
        menu_bar = MenuBarWidget(app_version=_APP_VERSION)
        status_bar = StatusBarWidget(
            theme_manager=theme_manager, platform_kind=platform_kind, app_version=_APP_VERSION
        )
        shell = MainWindowShell(
            menu_bar=menu_bar,
            status_bar=status_bar,
            benchmark_workspace_factory=QWidget,
            task_editor_workspace_factory=QWidget,
            app_version=_APP_VERSION,
        )
        qtbot.addWidget(shell)  # type: ignore[attr-defined]  # qtbot fixture is untyped upstream
        # Shown so child-widget `isVisible()` reflects real on-screen state (offscreen Qt
        # platform plugin -- see tests/conftest.py's Qt parity rig) rather than the
        # ancestor-realization-pending `False` every child widget reports before its
        # top-level window has ever been shown.
        shell.show()

        settings_requested_calls: list[None] = []
        about_requested_calls: list[None] = []

        close_handler = CloseHandler(
            gateway=gateway,
            event_bus=event_bus,
            notifications=notifications,
            on_confirmed_quit=lambda: None,
            shutdown_timeout_ms=shutdown_timeout_ms,
        )
        controller = MainWindowController(
            gateway=gateway,
            event_bus=event_bus,
            workspace=workspace,
            notifications=notifications,
            file_system_actions=file_system_actions,
            shell=shell,
            close_handler=close_handler,
            app_version=_APP_VERSION,
            settings_requested=lambda: settings_requested_calls.append(None),
            about_requested=lambda: about_requested_calls.append(None),
        )
        controller.bind()
        return MainWindowHarness(
            controller=controller,
            shell=shell,
            close_handler=close_handler,
            gateway=gateway,
            event_bus=event_bus,
            workspace=workspace,
            notifications=notifications,
            settings_requested_calls=settings_requested_calls,
            about_requested_calls=about_requested_calls,
        )

    return _make
