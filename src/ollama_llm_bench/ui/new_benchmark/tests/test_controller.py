"""Controller <-> Gateway persistence tests (STORY-054-AC-1)."""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager


def test_mode_selector_restores_and_persists_last_mode_via_gateway(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-054-AC-1

    Given ``benchmark.last_mode`` was previously persisted as "tasks", the mode
    selector restores TASKS at construction; and when the user then selects
    GRADED, the controller calls ``NewBenchmarkGateway.set_setting`` with
    ``("benchmark.last_mode", "graded")``.
    """
    # Arrange
    gateway = FakeNewBenchmarkGateway()
    gateway.set_setting_value("benchmark.last_mode", "tasks")
    collaborators = NewBenchmarkCollaborators(
        gateway=gateway,
        event_bus=fake_event_bus,
        task_file_loader=FakeTaskFileLoader(),
        mode_visibility_policy=real_mode_visibility_policy,
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    # Act
    widget = make_new_benchmark_widget(collaborators=collaborators)
    qtbot.addWidget(widget)
    view = widget
    assert isinstance(view, NewBenchmarkView)
    # Assert (restore clause)
    assert view.mode_selector.selected_mode == RunMode.TASKS
    # Act (a genuine user mode change)
    view.mode_selector.select_mode_for_test(RunMode.GRADED)
    # Assert (persistence clause)
    assert ("benchmark.last_mode", "graded") in gateway.recorded_set_settings
