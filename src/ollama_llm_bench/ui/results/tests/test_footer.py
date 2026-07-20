"""Colocated unit tests for ``FooterController`` (STORY-061-AC-3, AC-4, AC-5)."""

import pytest

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus
from ollama_llm_bench.ui.results._internal.footer import FooterController
from ollama_llm_bench.ui.results.models import FooterViewModel, ResultCollaborators
from ollama_llm_bench.ui.results.tests.conftest import (
    FakeClipboard,
    FakeEventBus,
    FakeExportFilenameHelper,
    FakeFileSystemActions,
    FakeNativePickers,
    FakeNotificationService,
    FakeResultGateway,
    make_run,
)


def _completed_result(run_id: int) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=1,
        run_id=run_id,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=ResultStatus.COMPLETED,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _build_collaborators(
    *,
    gateway: FakeResultGateway | None = None,
    bus: FakeEventBus | None = None,
    file_system_actions: FakeFileSystemActions | None = None,
    native_pickers: FakeNativePickers | None = None,
    notifications: FakeNotificationService | None = None,
) -> ResultCollaborators:
    return ResultCollaborators(
        bus=bus or FakeEventBus(),
        gateway=gateway or FakeResultGateway(),
        native_pickers=native_pickers or FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=file_system_actions or FakeFileSystemActions(),
        notifications=notifications or FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
    )


@pytest.mark.parametrize(
    ("active_tab", "expected_buttons"),
    [
        ("summary", ("Export CSV", "Export Markdown")),
        ("details", ("Export CSV", "Export Markdown")),
        ("charts", ("Export PNG", "Export SVG")),
        ("run_analysis", ("Export Markdown",)),
    ],
)
def test_export_cluster_per_active_tab(active_tab: str, expected_buttons: tuple[str, ...]) -> None:
    """Proves: STORY-061-AC-3

    The footer's export-button cluster matches the active tab's content kind.
    """
    # Arrange
    run = make_run(1)
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (_completed_result(1),)})
    footer = FooterController(collaborators=_build_collaborators(gateway=gateway))
    # Act
    vm = footer.set_context(run_id=1, active_tab=active_tab, live=False)
    # Assert
    assert vm.export_buttons == expected_buttons


def test_exports_disabled_while_run_non_terminal() -> None:
    """Proves: STORY-061-AC-4

    Every export is disabled with the "Disabled — a benchmark is in progress."
    tooltip while any run is non-terminal (``live=True``), and re-enables once
    the run reaches a terminal state.
    """
    # Arrange
    run = make_run(1)
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (_completed_result(1),)})
    footer = FooterController(collaborators=_build_collaborators(gateway=gateway))
    # Act
    live_vm = footer.set_context(run_id=1, active_tab="summary", live=True)
    # Assert
    assert live_vm.exports_enabled is False
    assert live_vm.disabled_tooltip == "Disabled — a benchmark is in progress."
    # Act -- the run reaches a terminal state
    idle_vm = footer.set_context(run_id=1, active_tab="summary", live=False)
    # Assert
    assert idle_vm.exports_enabled is True
    assert idle_vm.disabled_tooltip is None


def test_exports_disabled_for_empty_run_with_no_completed_results() -> None:
    """Proves: STORY-061-AC-4

    Covers EC-RES-1 (empty-run mechanism): a run with zero completed results
    disables exports with the "No completed results to export yet" tooltip.
    """
    # Arrange
    run = make_run(1)
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: ()})
    footer = FooterController(collaborators=_build_collaborators(gateway=gateway))
    # Act
    vm = footer.set_context(run_id=1, active_tab="summary", live=False)
    # Assert
    assert vm.exports_enabled is False
    assert vm.disabled_tooltip == "No completed results to export yet"


def test_export_click_write_failure_keeps_toggle_on_and_shows_error() -> None:
    """Proves: STORY-061-AC-5

    Covers EC-RES-5 (write flow): a failed direct write shows a blocking
    error and leaves the save-directly toggle unchanged (still on).
    """
    # Arrange
    run = make_run(1, run_name="My Run")
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (_completed_result(1),)})
    gateway.set_setting("ui.export_save_directly", "true")
    notifications = FakeNotificationService()
    fs_actions = FakeFileSystemActions(fail_write=True)
    footer = FooterController(
        collaborators=_build_collaborators(
            gateway=gateway, file_system_actions=fs_actions, notifications=notifications
        )
    )
    footer.set_context(run_id=1, active_tab="summary", live=False)
    # Act
    footer.on_export_clicked("Export CSV")
    # Assert
    assert notifications.errors == [("The export could not be saved.", True)]
    assert gateway.get_setting("ui.export_save_directly") == "true"


def test_export_click_empty_sanitised_name_falls_back_to_run_id(
    msgspec_unused: None = None,
) -> None:
    """Proves: STORY-061-AC-5

    Covers EC-RES-6 (write flow): a run whose name sanitises to an empty
    string falls back to ``Run_<run_id>`` in the written export filename --
    proving the footer delegates filename composition to the
    ``ExportFilenameHelper`` rather than re-deriving it.
    """
    # Arrange
    run = make_run(1, run_name="....")
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (_completed_result(1),)})
    gateway.set_setting("ui.export_save_directly", "true")
    fs_actions = FakeFileSystemActions()
    footer = FooterController(
        collaborators=_build_collaborators(gateway=gateway, file_system_actions=fs_actions)
    )
    footer.set_context(run_id=1, active_tab="summary", live=False)
    # Act
    footer.on_export_clicked("Export CSV")
    # Assert
    written_paths = list(fs_actions.written)
    assert len(written_paths) == 1
    assert "Run_1_Summary.csv" in written_paths[0]


def test_save_destination_toggle_direct_vs_picker() -> None:
    """Proves: STORY-061-AC-5

    An export writes directly to the exports folder when the toggle is on,
    and opens a native Save Picker when it is off.
    """
    # Arrange
    run = make_run(1, run_name="My Run")
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (_completed_result(1),)})
    fs_actions = FakeFileSystemActions()
    native_pickers = FakeNativePickers(chosen_path="/desktop/My_Run_Summary.csv")
    footer = FooterController(
        collaborators=_build_collaborators(
            gateway=gateway, file_system_actions=fs_actions, native_pickers=native_pickers
        )
    )
    # Act -- toggle off (indirect/picker flow, the default)
    off_vm = footer.set_context(run_id=1, active_tab="summary", live=False)
    footer.on_export_clicked("Export CSV")
    # Assert
    assert off_vm.show_open_folder is False
    assert len(native_pickers.save_file_calls) == 1
    assert "/desktop/My_Run_Summary.csv" in fs_actions.written
    # Act -- toggle on (direct-write flow)
    footer.on_save_directly_toggled(checked=True)
    on_vm = footer.set_context(run_id=1, active_tab="summary", live=False)
    footer.on_export_clicked("Export CSV")
    # Assert
    assert on_vm.show_open_folder is True
    assert any(path.startswith("/app-data/exports/") for path in fs_actions.written)


def test_save_destination_toggle_parity_across_two_footer_instances() -> None:
    """Proves: STORY-061-AC-5

    Covers EC-WS-1 (detached footer parity): two independent
    FooterController instances sharing one gateway/bus stay in sync --
    toggling one flips the other's ``show_open_folder`` too, without a real
    DetachedTableWindow.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(1),), results_by_run_id={1: (_completed_result(1),)})
    footer_a = FooterController(collaborators=_build_collaborators(gateway=gateway, bus=bus))
    footer_b = FooterController(collaborators=_build_collaborators(gateway=gateway, bus=bus))
    footer_a.bind(object(), on_view_model_changed=lambda _vm: None)
    received: list[FooterViewModel] = []
    footer_b.bind(object(), on_view_model_changed=received.append)
    footer_a.set_context(run_id=1, active_tab="summary", live=False)
    footer_b.set_context(run_id=1, active_tab="summary", live=False)
    # Act
    footer_a.on_save_directly_toggled(checked=True)
    # Assert
    assert received
    assert received[-1].show_open_folder is True
