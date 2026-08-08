"""Colocated unit tests for ``ResultController`` (STORY-061-AC-1, AC-2, AC-5, AC-7)."""

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QPushButton, QTableView, QTabWidget
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus, RunMode, RunStatus
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_LIST_CHANGED,
    SIGNAL_RUN_STARTED,
    RunIdChangedEvent,
    RunStartedEvent,
)
from ollama_llm_bench.ui.results import make_result_widget
from ollama_llm_bench.ui.results._internal.controller import ResultController
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_task
from ollama_llm_bench.ui.results._internal.view import ResultView
from ollama_llm_bench.ui.results.models import ResultCollaborators
from ollama_llm_bench.ui.results.tests.conftest import (
    FakeClipboard,
    FakeEventBus,
    FakeExportFilenameHelper,
    FakeFileSystemActions,
    FakeModelFetcher,
    FakeNativePickers,
    FakeNotificationService,
    FakeProviderListSource,
    FakeResultGateway,
    make_run,
)

_RUN_1 = 1
_RUN_2 = 2
_RUN_3 = 3
_PERSISTED_ROW_COUNT = 2
_SELECTED_RESULT_ID = 2


def _run_started_event(run_id: int) -> RunStartedEvent:
    return RunStartedEvent(
        run_id=run_id,
        run_name=f"Run {run_id}",
        run_mode=RunMode.TASKS,
        started_at="2024-01-01T00:00:00Z",
        total_tasks=1,
        test_targets=(("11111111-1111-4111-8111-111111111111", "test-model"),),
    )


def test_run_selector_auto_jump_and_user_lock(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-1

    A ``_run_started`` event for a run not previously selected auto-selects it
    when unlocked; once the user manually selects a different run, a later
    ``_run_started`` does not move the selection.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway()
    controller = ResultController(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    # Act -- run 1 starts; unlocked, so it auto-selects
    gateway.add_run(make_run(_RUN_1))
    bus.emit(SIGNAL_RUN_LIST_CHANGED, object())
    bus.emit(SIGNAL_RUN_STARTED, _run_started_event(_RUN_1))
    # Assert
    assert controller.current_selected_run_id() == _RUN_1
    # Act -- the user manually picks a different run (not the active run 1)
    gateway.add_run(make_run(_RUN_2))
    bus.emit(SIGNAL_RUN_LIST_CHANGED, object())
    controller.on_dropdown_changed(_RUN_2)
    # Assert
    assert controller.current_selected_run_id() == _RUN_2
    # Act -- a later run start does not move the now-locked selection
    gateway.add_run(make_run(_RUN_3))
    bus.emit(SIGNAL_RUN_LIST_CHANGED, object())
    bus.emit(SIGNAL_RUN_STARTED, _run_started_event(_RUN_3))
    # Assert
    assert controller.current_selected_run_id() == _RUN_2


def test_dropdown_change_emits_and_external_selection_syncs(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-2

    A user dropdown change emits ``_run_id_changed`` carrying the chosen run
    id; a ``_run_id_changed`` arriving from another widget updates the
    selection without re-emitting the event.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(_RUN_1), make_run(_RUN_2)))
    controller = ResultController(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    # Act -- the user changes the dropdown selection
    controller.on_dropdown_changed(_RUN_1)
    # Assert
    emitted_run_id_changes = [
        payload for name, payload in bus.emitted if name == SIGNAL_RUN_ID_CHANGED
    ]
    assert emitted_run_id_changes[-1] == RunIdChangedEvent(run_id=_RUN_1, previous_run_id=_RUN_2)
    emitted_count_before = len(bus.emitted)
    # Act -- an external _run_id_changed arrives for the other run
    bus.emit(SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=_RUN_2, previous_run_id=_RUN_1))
    # Assert -- selection follows, with no re-emission
    assert controller.current_selected_run_id() == _RUN_2
    assert len(bus.emitted) == emitted_count_before + 1  # the external event itself only


def test_result_widget_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-7

    ``make_result_widget`` constructs and shows with no exception and no
    ``error``/``critical``-level structlog record.
    """
    # Arrange
    collaborators = ResultCollaborators(
        bus=FakeEventBus(),
        gateway=FakeResultGateway(runs=(make_run(_RUN_1),)),
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
        provider_source=FakeProviderListSource(),
        model_fetcher=FakeModelFetcher(),
    )
    # Act
    with structlog.testing.capture_logs() as logs:
        widget = make_result_widget(collaborators=collaborators)
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)
    # Assert
    assert widget.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_app_settings_changed_syncs_footer_across_two_result_widgets(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-5

    Covers EC-WS-1 (full-widget parity): toggling the save-destination
    checkbox on one ``make_result_widget`` instance updates the
    Open-Exports-Folder button's visibility on a second, independently
    constructed Result widget sharing the same Event Bus and gateway. This
    exercises the parent shell's eight-signal contract
    (``implementation_structure.md`` §4/§9) end to end through the public
    factory -- the parent ``ResultController`` delegates the
    ``_app_settings_changed`` subscription to its owned ``FooterController``
    collaborator (bound in ``ResultController.bind``), so the total
    subscription count for the parent shell is eight even though only seven
    ``bus.subscribe`` calls appear literally inside ``controller.py``.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(_RUN_1),))
    widget_a = make_result_widget(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    widget_b = make_result_widget(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    qtbot.addWidget(widget_a)
    qtbot.addWidget(widget_b)
    widget_a.show()
    widget_b.show()
    qtbot.wait(0)
    checkbox_a = cast("QCheckBox", widget_a.findChild(QCheckBox, "result_widget.save_directly"))
    open_folder_button_b = cast(
        "QPushButton", widget_b.findChild(QPushButton, "result_widget.open_exports_folder")
    )
    assert open_folder_button_b.isVisible() is False
    # Act -- toggling widget A's checkbox broadcasts `_app_settings_changed`
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        checkbox_a, Qt.MouseButton.LeftButton
    )
    qtbot.wait(0)
    # Assert -- widget B's footer re-reads the shared setting and re-renders
    assert open_folder_button_b.isVisible() is True


def test_manual_selection_while_idle_locks_against_later_auto_jump(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-1

    Given no run is currently live, when the user manually selects a run
    (not the -- nonexistent -- active run), then the selection locks; a
    later ``_run_started`` for a different run must not move it
    (``state_machine.md`` §4/§8: "user manually selects a run that is not
    the active run" locks regardless of whether a run is live at the time).
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(_RUN_1), make_run(_RUN_2)))
    controller = ResultController(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    # Act -- the user manually picks a run while no run is live
    controller.on_dropdown_changed(_RUN_1)
    # Assert
    assert controller.current_selected_run_id() == _RUN_1
    # Act -- a run starts for a different run; the locked selection must hold
    gateway.add_run(make_run(_RUN_3))
    bus.emit(SIGNAL_RUN_LIST_CHANGED, object())
    bus.emit(SIGNAL_RUN_STARTED, _run_started_event(_RUN_3))
    # Assert
    assert controller.current_selected_run_id() == _RUN_1


def test_mount_while_run_incomplete_seeds_live_and_disables_exports(qtbot: QtBot) -> None:
    """Proves: STORY-061-AC-4

    Given the widget mounts while a run is already ``INCOMPLETE`` (the only
    non-terminal persisted ``RunStatus``), when the initial state resolves,
    then the shell seeds ``live`` from that run rather than defaulting to
    idle, so exports render disabled immediately -- no reliance on a later
    ``_run_started`` event the mount itself never received.
    """
    # Arrange
    collaborators = ResultCollaborators(
        bus=FakeEventBus(),
        gateway=FakeResultGateway(runs=(make_run(_RUN_1, status=RunStatus.INCOMPLETE),)),
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
        provider_source=FakeProviderListSource(),
        model_fetcher=FakeModelFetcher(),
    )
    # Act
    widget = make_result_widget(collaborators=collaborators)
    qtbot.addWidget(widget)
    export_button = cast(
        "QPushButton", widget.findChild(QPushButton, "result_widget.export.export_csv")
    )
    # Assert
    assert export_button.isEnabled() is False
    assert export_button.toolTip() == "Disabled — a benchmark is in progress."


def test_no_run_state_disables_dropdown_and_tab_strip(qtbot: QtBot) -> None:
    """Proves: STORY-061 Definition of done

    Given the Data Store holds no runs, when the shell resolves its initial
    state, then the run-selector dropdown is empty and disabled and the tab
    strip is disabled -- the ``NoRun`` top-level state
    (``state_machine.md`` §1) the parent shell owns.
    """
    # Arrange
    collaborators = ResultCollaborators(
        bus=FakeEventBus(),
        gateway=FakeResultGateway(),
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
        provider_source=FakeProviderListSource(),
        model_fetcher=FakeModelFetcher(),
    )
    # Act
    widget = make_result_widget(collaborators=collaborators)
    qtbot.addWidget(widget)
    dropdown = cast("QComboBox", widget.findChild(QComboBox, "result_widget.run_dropdown"))
    tabs = cast("QTabWidget", widget.findChild(QTabWidget, "result_widget.tabs"))
    # Assert
    assert dropdown.count() == 0
    assert dropdown.isEnabled() is False
    assert tabs.isEnabled() is False


def _persisted_result(result_id: int) -> BenchmarkResult:
    """One COMPLETED result row of the shape the pipeline persists."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=_RUN_1,
        task_id=f"task_{result_id}",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Local provider",
        model_name="test-model",
        status=ResultStatus.COMPLETED,
        created_at="2024-01-01T00:00:00Z",
    )


def _bind_controller_showing_a_live_run(
    qtbot: QtBot, *, bus: FakeEventBus, gateway: FakeResultGateway
) -> tuple[ResultController, ResultView]:
    """Mount the Result shell with run 1 live and no rows persisted yet.

    Reproduces the exact state a real run start leaves the surface in: the
    run-started event has already selected run 1, so every later
    ``_sync_*_tab`` call sees an unchanged ``(run_id, run_mode)`` context and
    short-circuits.
    """
    gateway.add_run(make_run(_RUN_1, status=RunStatus.INCOMPLETE))
    controller = ResultController(
        collaborators=ResultCollaborators(
            bus=bus,
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
            notifications=FakeNotificationService(),
            export_filenames=FakeExportFilenameHelper(),
            provider_source=FakeProviderListSource(),
            model_fetcher=FakeModelFetcher(),
        )
    )
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    bus.emit(SIGNAL_RUN_STARTED, _run_started_event(_RUN_1))
    return controller, view


def test_run_terminal_recomputes_summary_details_and_charts(qtbot: QtBot) -> None:
    """Proves: STORY-085-AC-7

    A run finishing re-reads its now-persisted rows into the Summary and
    Details tables with no user interaction. The selected run and run mode are
    unchanged across the terminal event, so the shell's context change
    detection short-circuits every ``set_run_context`` call -- without the
    explicit ``recompute_and_push()`` calls the tables keep the empty state
    they had at run start.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway()
    _controller, view = _bind_controller_showing_a_live_run(qtbot, bus=bus, gateway=gateway)
    details_table = cast("QTableView", view.findChild(QTableView, "details_tab.table"))
    summary_table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    assert _row_count(details_table) == 0

    # Act -- the pipeline persists two rows, then the run settles
    gateway.set_tasks(_RUN_1, (make_task(task_id="task_1"), make_task(task_id="task_2")))
    gateway.set_results(_RUN_1, (_persisted_result(1), _persisted_result(2)))
    gateway.add_run(make_run(_RUN_1, status=RunStatus.COMPLETED))
    bus.emit(SIGNAL_RUN_FINISHED, object())

    # Assert
    assert _row_count(details_table) == _PERSISTED_ROW_COUNT
    assert _row_count(summary_table) > 0


def test_run_terminal_refresh_preserves_the_selected_details_row(qtbot: QtBot) -> None:
    """Proves: STORY-085 Definition of done

    The terminal refresh must not route through ``set_run_context``, which
    resets ``_selected_result_id``: a user who had a Details row selected while
    the run finished would silently lose the Task Detail Panel they were
    reading.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway()
    controller, _view = _bind_controller_showing_a_live_run(qtbot, bus=bus, gateway=gateway)
    gateway.set_tasks(_RUN_1, (make_task(task_id="task_1"), make_task(task_id="task_2")))
    gateway.set_results(_RUN_1, (_persisted_result(1), _persisted_result(2)))
    bus.emit(SIGNAL_RUN_FINISHED, object())
    controller._details_tab.on_row_selected(_SELECTED_RESULT_ID)
    assert controller._details_tab._selected_result_id == _SELECTED_RESULT_ID

    # Act -- a second terminal event arrives with the row still selected
    bus.emit(SIGNAL_RUN_FINISHED, object())

    # Assert
    assert controller._details_tab._selected_result_id == _SELECTED_RESULT_ID


def _row_count(table: QTableView) -> int:
    """The mounted table's current row count; 0 when no model is set yet."""
    model = table.model()
    return 0 if model is None else model.rowCount()
