"""Construction/interaction smoke test (STORY-054-AC-7)."""

from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager


def test_new_benchmark_widget_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-054-AC-7

    Constructed via its own factory with fakes for the Gateway and every
    declared non-store helper, mounted under qtbot and shown, no exception is
    raised, the widget reports isVisible(), and no error/critical-level
    structlog record is captured.
    """
    # Arrange
    gateway = FakeNewBenchmarkGateway()
    task_file_loader = FakeTaskFileLoader()
    native_pickers = FakeNativePickers()
    workspace = FakeWorkspaceController()
    collaborators = NewBenchmarkCollaborators(
        gateway=gateway,
        event_bus=fake_event_bus,
        task_file_loader=task_file_loader,
        mode_visibility_policy=real_mode_visibility_policy,
        run_validator=FakeRunValidator(),
        native_pickers=native_pickers,
        workspace=workspace,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    # Act
    with structlog.testing.capture_logs() as logs:
        widget = make_new_benchmark_widget(collaborators=collaborators)
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)
    # Assert
    assert widget.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)
