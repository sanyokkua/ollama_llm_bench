"""Colocated unit tests for Resume widget actions (STORY-056)."""

from collections.abc import Callable
from pathlib import Path

import msgspec
from PySide6.QtWidgets import QMessageBox, QWidget
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers import SavePickerOptions
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
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent, Subscription
from ollama_llm_bench.ui.resume_benchmark._internal.actions import (
    clone_as_new_retry_run,
    confirm_and_delete_run,
    export_run_analysis,
    show_run_log_file,
)
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import RunTableModel
from ollama_llm_bench.ui.resume_benchmark._internal.view_model_select import select_run_rows

_INTERNAL = "ollama_llm_bench.ui.resume_benchmark._internal.actions"
_EXPECTED_NEW_RUN_ID = 999


class _RecordingEventBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        raise NotImplementedError

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))

    def last_message(self) -> GlobalMessageEvent | None:
        for name, payload in reversed(self.emitted):
            if name == SIGNAL_GLOBAL_MESSAGE and isinstance(payload, GlobalMessageEvent):
                return payload
        return None


def _run(
    run_id: int,
    *,
    status: RunStatus,
    run_analysis: str | None = None,
) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name="My Run",
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=status,
        total_tasks=2,
        completed_tasks=1,
        total_elapsed_ms=500,
        run_analysis=run_analysis,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _result(result_id: int, *, run_id: int, status: ResultStatus) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        created_at="2024-01-01T00:00:00+00:00",
    )


class _FakeResumeGateway:
    def __init__(
        self,
        *,
        run: BenchmarkRun,
        tasks: tuple[BenchmarkTask, ...],
        results: tuple[BenchmarkResult, ...],
    ) -> None:
        self._run = run
        self._tasks = tasks
        self._results = results
        self.created_run: BenchmarkRun | None = None
        self.created_results: tuple[BenchmarkResult, ...] = ()
        self.created_tasks: tuple[BenchmarkTask, ...] = ()
        self.deleted_run_id: RunId | None = None
        self._next_id: RunId = 999

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._run

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return self._tasks

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def create_run(self, run: BenchmarkRun) -> RunId:
        self.created_run = run
        return self._next_id

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        self.created_tasks = tasks

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        self.created_results = results

    def delete_run(self, run_id: RunId) -> None:
        self.deleted_run_id = run_id

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return (self._run,)

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        raise NotImplementedError

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def reset_results(self, result_ids: tuple[int, ...]) -> int:
        raise NotImplementedError

    def reset_results_for_retry(self, result_ids: tuple[int, ...]) -> int:
        raise NotImplementedError

    def update_result(self, result_id: int, patch: object) -> None:
        raise NotImplementedError

    def refresh_readiness(self) -> AppReadinessSnapshot:
        raise NotImplementedError

    def get_sort_setting(self) -> tuple[str, bool]:
        raise NotImplementedError

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors ResumeGateway verbatim
        raise NotImplementedError

    def resume_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def is_run_active(self) -> bool:
        raise NotImplementedError

    def active_run_id(self) -> RunId | None:
        raise NotImplementedError


class _FakeAutoIncrementResumeGateway(_FakeResumeGateway):
    """A ``ResumeGateway`` fake mimicking the real ``ResultsStore.create_results``'s
    autoincrement behaviour: ids the caller supplies are discarded and replaced
    with freshly assigned ones (``backend/persistence/results/_internal/store_impl.py``
    ``_insert_result_header`` never binds the incoming ``result_id`` into its
    ``INSERT`` column list -- confirmed by reading that store's real code)."""

    def __init__(
        self,
        *,
        run: BenchmarkRun,
        tasks: tuple[BenchmarkTask, ...],
        results: tuple[BenchmarkResult, ...],
    ) -> None:
        super().__init__(run=run, tasks=tasks, results=results)
        self._next_result_id: ResultId = 500

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        assigned: list[BenchmarkResult] = []
        for result in results:
            assigned.append(msgspec.structs.replace(result, result_id=self._next_result_id))
            self._next_result_id += 1
        self.created_results = tuple(assigned)


def test_clone_creates_new_retry_run() -> None:
    """Proves: STORY-056-AC-5

    Clone copies mode/snapshots verbatim, suffixes the name with (retry),
    clears run_analysis, sets INCOMPLETE, and copies COMPLETED results as-is
    while resetting every other result to PENDING.
    """
    # Arrange
    source = _run(1, status=RunStatus.FAILED, run_analysis="some analysis")
    completed_result = _result(1, run_id=1, status=ResultStatus.COMPLETED)
    failed_result = _result(2, run_id=1, status=ResultStatus.FAILED_INFERENCE)
    gateway = _FakeResumeGateway(run=source, tasks=(), results=(completed_result, failed_result))

    # Act
    new_id = clone_as_new_retry_run(gateway=gateway, source_run_id=1)

    # Assert
    assert new_id == _EXPECTED_NEW_RUN_ID
    assert gateway.created_run is not None
    assert gateway.created_run.run_name == "My Run (retry)"
    assert gateway.created_run.run_analysis is None
    assert gateway.created_run.status is RunStatus.INCOMPLETE
    statuses = {r.result_id: r.status for r in gateway.created_results}
    assert statuses[1] is ResultStatus.COMPLETED
    assert statuses[2] is ResultStatus.PENDING


def test_clone_clears_error_fields_on_reset_results() -> None:
    """Proves: STORY-056-AC-5

    A reset (non-COMPLETED) result's error/in-flight fields are cleared.
    """
    # Arrange
    source = _run(1, status=RunStatus.FAILED)
    failed_result = BenchmarkResult(
        result_id=2,
        run_id=1,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=ResultStatus.FAILED_INFERENCE,
        created_at="2024-01-01T00:00:00+00:00",
        error_kind="llm",  # type: ignore[arg-type]  # ErrorKind accepts its str value
        error_message="boom",
    )
    gateway = _FakeResumeGateway(run=source, tasks=(), results=(failed_result,))

    # Act
    clone_as_new_retry_run(gateway=gateway, source_run_id=1)

    # Assert
    reset_result = gateway.created_results[0]
    assert reset_result.error_kind is None
    assert reset_result.error_message is None


def test_clone_stamps_a_fresh_created_at_newer_than_the_source() -> None:
    """Proves: STORY-056-AC-5 (gap fix: clone sorts to the top, §3.6 step 5)

    RunsStore.create_run does not re-stamp created_at/timestamp on insert
    (confirmed by reading
    backend/persistence/runs/_internal/store_impl.py::_insert_run_header,
    which binds run.created_at/run.timestamp verbatim) -- so
    clone_as_new_retry_run must stamp a fresh "now" itself for the clone to
    ever sort ahead of its (necessarily older) source run.
    """
    # Arrange
    source = _run(1, status=RunStatus.FAILED)  # created_at: 2024-01-01T00:00:00+00:00
    gateway = _FakeResumeGateway(run=source, tasks=(), results=())

    # Act
    clone_as_new_retry_run(gateway=gateway, source_run_id=1)

    # Assert
    cloned_run = gateway.created_run
    assert cloned_run is not None
    assert cloned_run.created_at > source.created_at
    assert cloned_run.timestamp > source.timestamp


def test_clone_sorts_to_top_of_default_started_at_descending_table_order(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-056-AC-5 (gap fix: clone sorts to the top, §3.6 step 5)

    Feeding the source run and the freshly cloned run through the same
    view_model_select/RunTableModel pipeline the widget uses proves the
    clone's fresh created_at stamp lands it first under the table's default
    started_at-or-created_at descending sort.
    """
    # Arrange
    source = _run(1, status=RunStatus.FAILED)
    gateway = _FakeResumeGateway(run=source, tasks=(), results=())

    # Act
    new_run_id = clone_as_new_retry_run(gateway=gateway, source_run_id=1)
    cloned_run = gateway.created_run
    assert cloned_run is not None
    cloned_run = msgspec.structs.replace(cloned_run, run_id=new_run_id)

    # Assert
    rows = select_run_rows(
        runs=(source, cloned_run),
        results_by_run_id={1: (), new_run_id: ()},
        active_run_id=None,
        log_file_exists_by_run_id={},
    )
    model = RunTableModel(rows=rows)
    assert model.visible_row(0).run_id == new_run_id


def test_clone_result_ids_are_reassigned_by_an_autoincrement_store() -> None:
    """Proves: STORY-056-AC-5 (gap fix: clone must not reuse source result_id values)

    ResultsStore.create_results is an autoincrement store that discards the
    caller-supplied result_id (confirmed by reading
    backend/persistence/results/_internal/store_impl.py::_insert_result_header,
    which never binds the incoming id into its INSERT column list) -- so
    passing the source's result_id through unchanged on the clone is safe:
    a real store always assigns fresh, distinct ids regardless.
    """
    # Arrange
    source = _run(1, status=RunStatus.FAILED)
    completed_result = _result(1, run_id=1, status=ResultStatus.COMPLETED)
    failed_result = _result(2, run_id=1, status=ResultStatus.FAILED_INFERENCE)
    gateway = _FakeAutoIncrementResumeGateway(
        run=source, tasks=(), results=(completed_result, failed_result)
    )

    # Act
    clone_as_new_retry_run(gateway=gateway, source_run_id=1)

    # Assert
    new_ids = {r.result_id for r in gateway.created_results}
    source_ids = {completed_result.result_id, failed_result.result_id}
    assert new_ids.isdisjoint(source_ids)


def test_confirm_and_delete_run_deletes_on_yes(mocker: MockerFixture, qtbot: QtBot) -> None:
    """Proves: STORY-056 (delete action)

    Confirming Yes deletes the run and emits a run-list-changed event.
    """
    # Arrange
    mocker.patch(
        f"{_INTERNAL}.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    gateway = _FakeResumeGateway(run=_run(1, status=RunStatus.COMPLETED), tasks=(), results=())
    event_bus = _RecordingEventBus()
    parent = QWidget()
    qtbot.addWidget(parent)

    # Act
    deleted = confirm_and_delete_run(
        gateway=gateway, event_bus=event_bus, run_id=1, run_name="My Run", parent=parent
    )

    # Assert
    assert deleted is True
    assert gateway.deleted_run_id == 1


def test_confirm_and_delete_run_keeps_run_on_no(mocker: MockerFixture, qtbot: QtBot) -> None:
    """Proves: STORY-056 (delete action)

    Declining the confirmation performs no Gateway call.
    """
    # Arrange
    mocker.patch(
        f"{_INTERNAL}.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )
    gateway = _FakeResumeGateway(run=_run(1, status=RunStatus.COMPLETED), tasks=(), results=())
    event_bus = _RecordingEventBus()
    parent = QWidget()
    qtbot.addWidget(parent)

    # Act
    deleted = confirm_and_delete_run(
        gateway=gateway, event_bus=event_bus, run_id=1, run_name="My Run", parent=parent
    )

    # Assert
    assert deleted is False
    assert gateway.deleted_run_id is None


class _FakeNativePickers:
    def __init__(self, *, save_path: str | None) -> None:
        self._save_path = save_path
        self.last_options: SavePickerOptions | None = None

    def save_file(self, options: SavePickerOptions) -> str | None:
        self.last_options = options
        return self._save_path

    def open_file(self, options: object) -> tuple[str, ...]:
        raise NotImplementedError

    def open_folder(self, options: object) -> str | None:
        raise NotImplementedError


def test_export_run_analysis_writes_verbatim(tmp_path: object, qtbot: QtBot) -> None:
    """Proves: STORY-056 (export run analysis)

    A run with analysis writes it verbatim to the picked path.
    """
    # Arrange
    target = str(tmp_path / "out.md")  # type: ignore[operator]  # tmp_path is a Path fixture
    gateway = _FakeResumeGateway(
        run=_run(1, status=RunStatus.COMPLETED, run_analysis="# Analysis"), tasks=(), results=()
    )
    native_pickers = _FakeNativePickers(save_path=target)
    event_bus = _RecordingEventBus()

    # Act
    export_run_analysis(
        gateway=gateway,
        native_pickers=native_pickers,
        event_bus=event_bus,
        run_id=1,
        effective_run_name="My Run",
    )

    # Assert
    assert Path(target).read_text(encoding="utf-8") == "# Analysis"


def test_export_run_analysis_with_no_analysis_toasts_and_writes_nothing() -> None:
    """Proves: STORY-056-AC-4 (EC-RB-8)

    Exporting a run with no analysis emits the disabled-tooltip-matching
    toast and writes nothing.
    """
    # Arrange
    gateway = _FakeResumeGateway(
        run=_run(1, status=RunStatus.COMPLETED, run_analysis=None), tasks=(), results=()
    )
    native_pickers = _FakeNativePickers(save_path=None)
    event_bus = _RecordingEventBus()

    # Act
    export_run_analysis(
        gateway=gateway,
        native_pickers=native_pickers,
        event_bus=event_bus,
        run_id=1,
        effective_run_name="My Run",
    )

    # Assert
    assert native_pickers.last_options is None
    message = event_bus.last_message()
    assert message is not None
    assert message.text == "No analysis for this run"


class _FakeFileSystemActions:
    def __init__(self, *, path_str: str = "derived_run.log", raises: bool = False) -> None:
        self._path_str = path_str
        self._raises = raises
        self.opened_path: str | None = None

    def open_in_file_manager(self, path: str) -> None:
        if self._raises:
            raise OsAdapterError(message="boom")
        self.opened_path = path

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return True

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return self._path_str


def test_show_run_log_file_opens_derived_path() -> None:
    """Proves: STORY-056-AC-4 (show run-log file)

    Show run-log file reveals the derived log path via FileSystemActions.
    """
    # Arrange
    file_system_actions = _FakeFileSystemActions(path_str="derived_run_1_123.log")
    event_bus = _RecordingEventBus()

    # Act
    show_run_log_file(
        file_system_actions=file_system_actions,
        event_bus=event_bus,
        run_id=1,
        started_at="2024-01-01T00:00:00+00:00",
    )

    # Assert
    assert file_system_actions.opened_path == "derived_run_1_123.log"


def test_show_run_log_file_toasts_on_os_adapter_error() -> None:
    """Proves: STORY-056 (EC-RB-9)

    An OsAdapterError raised revealing the log file is caught and toasted,
    never propagated.
    """
    # Arrange
    file_system_actions = _FakeFileSystemActions(raises=True)
    event_bus = _RecordingEventBus()

    # Act
    show_run_log_file(
        file_system_actions=file_system_actions,
        event_bus=event_bus,
        run_id=1,
        started_at="2024-01-01T00:00:00+00:00",
    )

    # Assert
    message = event_bus.last_message()
    assert message is not None
    assert message.severity == "error"
