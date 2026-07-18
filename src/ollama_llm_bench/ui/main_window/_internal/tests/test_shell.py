"""Unit tests for ``_internal/shell.py`` and the ``make_main_window`` factory
(STORY-053-AC-4, STORY-053-AC-9).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from PySide6.QtWidgets import QWidget
import structlog

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.backend.domain import ReadinessState
from ollama_llm_bench.ui.main_window import make_main_window
from ollama_llm_bench.ui.main_window._internal.menu_bar import MenuBarWidget
from ollama_llm_bench.ui.main_window._internal.shell import MainWindowShell
from ollama_llm_bench.ui.main_window._internal.status_bar import StatusBarWidget
from ollama_llm_bench.ui.main_window._internal.tests.conftest import (
    FakeEventBus,
    FakeMainWindowGateway,
    FakeWorkspaceController,
)
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

_APP_VERSION = "9.9.9"


@contextmanager
def _isolated_structlog_defaults() -> Iterator[None]:
    """Snapshot and restore ``structlog``'s process-global configuration.

    ``structlog.testing.capture_logs()`` only swaps the processor chain -- it never resets
    ``wrapper_class``. If an earlier test in the full suite has already called
    ``ollama_llm_bench.backend.infra.configure_logging(...)`` (which installs a process-global
    ``structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))``
    with no teardown), every ``DEBUG``-level call anywhere in the process -- including this
    test's own -- becomes a silent no-op regardless of ``capture_logs()``, making this test's
    outcome depend on execution order across module boundaries. Resetting to structlog's
    built-in (unfiltered) defaults for the duration of this test, then restoring whatever was
    configured before, keeps this test's result independent of any other test's global state.
    """
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.configure(**original_config)


def _make_view_model(*, running_pill_visible: bool) -> MainWindowViewModel:
    return MainWindowViewModel(
        window_title="Ollama LLM Bench v9.9.9",
        active_workspace="benchmark",
        settings_action_enabled=not running_pill_visible,
        running_pill_visible=running_pill_visible,
        running_pill_label="my-run" if running_pill_visible else "",
        health_state=ReadinessState.READY,
        health_tooltip="",
        health_dot_clickable=not running_pill_visible,
        toast_text="",
    )


def test_benchmark_layout_reflows_on_run_lifecycle(
    qtbot: object, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> None:
    """Proves: STORY-053-AC-4

    Given the Benchmark workspace is active and no run is active,
    when a ``_run_started`` event is delivered,
    then the left run-configuration panel is removed from the layout and the centre panel
    expands; and when the run reaches a terminal state, the left panel reappears and the idle
    three-panel layout is restored.
    """
    # Arrange
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
    shell.show()  # child-widget isVisible() needs a shown top-level ancestor to be meaningful
    # PySide6-stubs' `findChild` return type is solved from an unconstrained TypeVar (bound
    # only via the runtime `type` argument, not `type[T]`), so mypy cannot infer it as
    # `QWidget | None` here; cast to the real contract (see
    # adapters/workspace_controller/_internal/controller.py for the same pattern).
    left_slot = cast("QWidget | None", shell.findChild(QWidget, "benchmark_left_slot_placeholder"))
    assert left_slot is not None

    # Act / Assert — idle: the left slot starts visible
    shell.apply_view_model(_make_view_model(running_pill_visible=False))
    assert left_slot.isVisible()

    # Act / Assert — a run starts: the left slot is removed from the visible layout
    shell.apply_view_model(_make_view_model(running_pill_visible=True))
    assert not left_slot.isVisible()

    # Act / Assert — the run reaches a terminal state: the left slot reappears
    shell.apply_view_model(_make_view_model(running_pill_visible=False))
    assert left_slot.isVisible()


def test_main_window_constructs_and_shows_with_no_error_logs(  # noqa: PLR0913  # AC-9
    # requires a fake for every one of `make_main_window`'s ten collaborators; grouping
    # them into a struct would defeat pytest's per-fixture override mechanism
    qtbot: object,
    event_bus: FakeEventBus,
    gateway: FakeMainWindowGateway,
    workspace: FakeWorkspaceController,
    notifications: FakeNotificationService,
    file_system_actions: FileSystemActions,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-053-AC-9

    Given the shell is constructed with fakes for every declared collaborator and mounted
    under ``qtbot``,
    when it is shown,
    then no exception is raised, the shell reports ``isVisible()``, no ``error``/``critical``
    ``structlog`` record is captured, and at least one ``DEBUG``-level construction event is
    captured.
    """
    # Arrange / Act
    with _isolated_structlog_defaults(), structlog.testing.capture_logs() as captured_logs:
        window = make_main_window(
            event_bus=event_bus,
            gateway=gateway,
            workspace=workspace,
            notifications=notifications,
            file_system_actions=file_system_actions,
            benchmark_workspace_factory=QWidget,
            task_editor_workspace_factory=QWidget,
            app_version=_APP_VERSION,
            theme_manager=theme_manager,
            platform_kind=platform_kind,
        )
        qtbot.addWidget(window)  # type: ignore[attr-defined]  # qtbot fixture is untyped upstream
        window.show()
        qtbot.wait(0)  # type: ignore[attr-defined]  # qtbot fixture is untyped upstream

    # Assert
    assert window.isVisible()
    error_or_critical_logs = [
        record for record in captured_logs if record["log_level"] in {"error", "critical"}
    ]
    assert error_or_critical_logs == []
    debug_logs = [record for record in captured_logs if record["log_level"] == "debug"]
    assert len(debug_logs) >= 1
