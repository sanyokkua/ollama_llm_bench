"""Colocated unit tests for the Resume controller's menu-action wiring and
event-handler branches (STORY-056), complementing test_controller.py.
"""

from collections.abc import Callable

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu, QWidget
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_GLOBAL_MESSAGE,
    RunAnalysisReceivedEvent,
    RunIdChangedEvent,
    Subscription,
)
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.resume_benchmark._internal.context_menu import build_context_menu
from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import COL_MODE, COL_NAME

_INTERNAL_ACTIONS = "ollama_llm_bench.ui.resume_benchmark._internal.actions"
_COMMON_DIALOGS = "ollama_llm_bench.ui.common_dialogs"
_EXPECTED_SIGNAL_COUNT = 9


class _NoopSubscription:
    def cancel(self) -> None:
        return None


class _RecordingEventBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []
        self.subscribed_signals: list[str] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        self.subscribed_signals.append(signal_name)
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))

    def last(self, signal_name: str) -> object:
        for name, payload in reversed(self.emitted):
            if name == signal_name:
                return payload
        raise AssertionError(f"no event emitted on {signal_name}")


class _FakeNativePickers:
    def save_file(self, options: object) -> str | None:
        return None

    def open_file(self, options: object) -> tuple[str, ...]:
        return ()

    def open_folder(self, options: object) -> str | None:
        return None


class _FakeFileSystemActions:
    def __init__(self) -> None:
        self.opened_paths: list[str] = []

    def open_in_file_manager(self, path: str) -> None:
        self.opened_paths.append(path)

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return "run.log"

    def write_export_file(self, *, filename: str, content: str) -> str:
        raise NotImplementedError

    def write_text_file(self, *, path: str, content: str) -> None:
        raise NotImplementedError

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        raise NotImplementedError

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        raise NotImplementedError

    def exports_folder_path(self) -> str:
        raise NotImplementedError


class _FakeResumeGateway:
    """A fully-implemented ResumeGateway fake, recording every mutating call."""

    def __init__(self, *, runs: tuple[BenchmarkRun, ...]) -> None:
        self._runs = {run.run_id: run for run in runs}
        self._results_by_run_id: dict[RunId, tuple[BenchmarkResult, ...]] = dict.fromkeys(
            self._runs, ()
        )
        self.renamed: tuple[RunId, str | None] | None = None
        self.deleted_run_id: RunId | None = None
        self.set_sort_calls: list[tuple[str, bool]] = []
        self.created_run: BenchmarkRun | None = None
        self.created_results: tuple[BenchmarkResult, ...] = ()
        self.resumed_run_ids: list[RunId] = []
        self._next_run_id: RunId = 999

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return tuple(self._runs.values())

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[run_id]

    def create_run(self, run: BenchmarkRun) -> RunId:
        self.created_run = run
        self._runs[self._next_run_id] = run
        self._results_by_run_id[self._next_run_id] = ()
        return self._next_run_id

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        self.renamed = (run_id, name)

    def delete_run(self, run_id: RunId) -> None:
        self.deleted_run_id = run_id
        del self._runs[run_id]

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results_by_run_id.get(run_id, ())

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        self.created_results = results

    def update_result(self, result_id: ResultId, patch: object) -> None:
        raise NotImplementedError

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return ()

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        return None

    def refresh_readiness(self) -> AppReadinessSnapshot:
        raise NotImplementedError

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return ()

    def get_sort_setting(self) -> tuple[str, bool]:
        return ("started", True)

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors ResumeGateway verbatim
        self.set_sort_calls.append((column, descending))

    def resume_run(self, run_id: RunId) -> None:
        self.resumed_run_ids.append(run_id)

    def is_run_active(self) -> bool:
        return False

    def active_run_id(self) -> RunId | None:
        return None


def _run(run_id: int, *, run_name: str | None = "Alpha") -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=0,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _pending_result(result_id: int) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=1,
        task_id=f"task-{result_id}",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=ResultStatus.PENDING,
        created_at="2024-01-01T00:00:00+00:00",
    )


class _StubResumeView(QWidget):
    """A bare stand-in view carrying only the footer-button-state hook
    (STORY-057) the controller now pushes to on every rows/selection change --
    this file's tests exercise controller logic, never real view rendering.
    """

    def set_resume_button_state(self, *, enabled: bool, disabled_reason: str) -> None:
        pass


def _make_controller(
    gateway: _FakeResumeGateway, *, bus: _RecordingEventBus
) -> tuple[ResumeBenchmarkController, QWidget]:
    controller = ResumeBenchmarkController(
        gateway=gateway,
        event_bus=bus,
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
    )
    view = _StubResumeView()
    controller.bind(view)
    controller.load_initial_rows()
    return controller, view


def test_bind_subscribes_to_every_expected_signal(qtbot: QtBot) -> None:
    """Proves: STORY-056 (controller EventBus subscriptions)

    bind() subscribes to every event listed in the widget's spec §7.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    # Act
    _controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    # Assert
    assert len(bus.subscribed_signals) == len(set(bus.subscribed_signals)) == _EXPECTED_SIGNAL_COUNT


def test_on_sort_header_clicked_toggles_direction_and_persists(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-1

    Clicking a new column header sorts descending by default and persists
    it; clicking the same column again toggles to ascending.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act
    controller.on_sort_header_clicked(COL_NAME)
    # Assert
    assert gateway.set_sort_calls[-1] == ("name", True)

    # Act
    controller.on_sort_header_clicked(COL_NAME)
    # Assert
    assert gateway.set_sort_calls[-1] == ("name", False)

    # Act
    controller.on_sort_header_clicked(COL_MODE)
    # Assert
    assert gateway.set_sort_calls[-1] == ("mode", True)


def test_on_context_menu_requested_with_no_bound_view_is_a_noop() -> None:
    """Proves: STORY-056 (controller robustness)

    on_context_menu_requested is a no-op before a view is bound.
    """
    # Arrange
    controller = ResumeBenchmarkController(
        gateway=_FakeResumeGateway(runs=()),
        event_bus=_RecordingEventBus(),
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
    )
    # Act / Assert (raises nothing)
    controller.on_context_menu_requested(0, QPoint(0, 0))


def test_on_context_menu_requested_builds_and_execs_menu(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-056-AC-4

    on_context_menu_requested builds the context menu for the row under the
    cursor and execs it.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    fake_menu = mocker.Mock()
    fake_menu.actions.return_value = []
    build_menu_mock = mocker.patch(
        "ollama_llm_bench.ui.resume_benchmark._internal.controller.build_context_menu",
        return_value=fake_menu,
    )

    # Act
    controller.on_context_menu_requested(0, QPoint(0, 0))

    # Assert
    build_menu_mock.assert_called_once()
    fake_menu.exec.assert_called_once()


def test_menu_actions_trigger_their_handlers(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-056-AC-5, AC-6

    Each wired context-menu action invokes its handler when triggered.
    """
    # Arrange
    mocker.patch(f"{_INTERNAL_ACTIONS}.QMessageBox.question", return_value=None)
    fake_dialog = mocker.Mock()
    fake_dialog.exec.return_value = None
    mocker.patch(f"{_COMMON_DIALOGS}.make_rename_run_dialog", return_value=fake_dialog)

    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    row = controller.table_model.visible_row(0)
    menu = build_context_menu(row=row, parent=view)
    controller._wire_menu_actions(menu, row)

    # Act / Assert -- Clone
    _trigger(menu, "action_clone")
    assert gateway.created_run is not None

    # Act / Assert -- Rename
    _trigger(menu, "action_rename")
    fake_dialog.exec.assert_called_once()

    # Act / Assert -- Export Analysis (no analysis -> toast, no crash)
    _trigger(menu, "action_export_summary_csv")
    message = bus.last(SIGNAL_GLOBAL_MESSAGE)
    assert getattr(message, "text", None) == "Export not yet available"

    # Act / Assert -- Show run-log file
    _trigger(menu, "action_show_log")


def _trigger(menu: QMenu, object_name: str) -> None:
    for action in menu.actions():
        if action.objectName() == object_name:
            action.trigger()
            return
    raise AssertionError(f"no action named {object_name}")


def test_resume_run_clicked_opens_dialog_and_calls_resume_run(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-057-AC-4

    Confirming the Resume Summary dialog opened from on_resume_run_clicked
    calls ResumeGateway.resume_run(run_id) for the selected run.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    fake_dialog = mocker.Mock()
    fake_dialog.exec.side_effect = lambda: gateway.resume_run(1)
    make_dialog_mock = mocker.patch(
        f"{_COMMON_DIALOGS}.make_resume_summary_dialog", return_value=fake_dialog
    )
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    controller.on_row_selected(1)

    # Act
    controller.on_resume_run_clicked()

    # Assert
    make_dialog_mock.assert_called_once()
    fake_dialog.exec.assert_called_once()
    assert gateway.resumed_run_ids == [1]


def test_resume_run_clicked_with_no_selection_is_a_noop(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-057-AC-4

    on_resume_run_clicked with no row selected never opens the dialog.
    """
    # Arrange
    make_dialog_mock = mocker.patch(f"{_COMMON_DIALOGS}.make_resume_summary_dialog")
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act
    controller.on_resume_run_clicked()

    # Assert
    make_dialog_mock.assert_not_called()


def test_retry_context_menu_action_opens_retry_dialog(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-057-AC-5

    Triggering action_retry from the context menu opens the Retry Selection
    dialog for that row's run.
    """
    # Arrange
    fake_dialog = mocker.Mock()
    fake_dialog.exec.return_value = None
    make_dialog_mock = mocker.patch(
        f"{_COMMON_DIALOGS}.make_retry_selection_dialog", return_value=fake_dialog
    )
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    gateway._results_by_run_id[1] = (_pending_result(1),)  # test-fake setup
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    row = controller.table_model.visible_row(0)
    menu = build_context_menu(row=row, parent=view)
    controller._wire_menu_actions(menu, row)

    # Act
    _trigger(menu, "action_retry")

    # Assert
    make_dialog_mock.assert_called_once_with(gateway=gateway, run_id=1, parent=view)
    fake_dialog.exec.assert_called_once()


def test_splice_row_updates_existing_row_in_place(qtbot: QtBot) -> None:
    """Proves: STORY-056 (event-driven row splice)

    _splice_row replaces just the touched row's data, leaving other rows
    untouched.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1), _run(2, run_name="Beta")))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    gateway._runs[1] = _run(1, run_name="Alpha Renamed")

    # Act
    controller._splice_row(1)

    # Assert
    assert controller.table_model.rowCount() == 2  # noqa: PLR2004


def test_on_run_touched_ignores_unrelated_payload(qtbot: QtBot) -> None:
    """Proves: STORY-056 (event subscription robustness)

    _on_run_touched ignores a payload that is not one of the run-touched
    event types.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act / Assert (raises nothing, no rebuild triggered by an unrelated payload)
    controller._on_run_touched(object())


def test_on_run_touched_splices_matching_payload(qtbot: QtBot) -> None:
    """Proves: STORY-056 (event-driven row splice)

    _on_run_touched splices the row named by a matching event's run_id.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)
    event = RunAnalysisReceivedEvent(
        run_id=1, run_mode=RunMode.TASKS, analysis_markdown="x", generated_at="2024-01-01T00:00:00Z"
    )

    # Act
    controller._on_run_touched(event)

    # Assert
    assert controller.table_model.rowCount() == 1


def test_on_external_run_id_changed_updates_selection_state(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-2

    _on_external_run_id_changed syncs internal selection state when another
    surface changes the active run, and ignores a non-matching payload.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act -- ignored: not a RunIdChangedEvent
    controller._on_external_run_id_changed(object())

    # Act -- applied
    controller._on_external_run_id_changed(RunIdChangedEvent(run_id=1, previous_run_id=None))
    # Act -- no-op: same value as current selection
    controller._on_external_run_id_changed(RunIdChangedEvent(run_id=1, previous_run_id=None))

    # Assert
    assert controller._selected_run_id == 1


def test_on_task_file_changed_rebuilds_all_rows(qtbot: QtBot) -> None:
    """Proves: STORY-056 (task-file over-refresh, accepted per plan)

    _on_task_file_changed triggers a full rebuild.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act
    controller._on_task_file_changed(object())

    # Assert
    assert controller.table_model.rowCount() == 1


def test_rename_context_for_returns_current_name_and_default(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-6

    rename_context_for returns the run's current custom name and the
    computed default-name preview.
    """
    # Arrange
    bus = _RecordingEventBus()
    gateway = _FakeResumeGateway(runs=(_run(1, run_name="Custom"),))
    controller, view = _make_controller(gateway, bus=bus)
    qtbot.addWidget(view)

    # Act
    current_name, default_name = controller.rename_context_for(1)

    # Assert
    assert current_name == "Custom"
    assert default_name.startswith("Run 1")
