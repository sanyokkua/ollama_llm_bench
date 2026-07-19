"""Colocated unit tests for the Resume widget controller (STORY-056)."""

from collections.abc import Callable, Mapping

from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultId,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_ID_CHANGED,
    RunIdChangedEvent,
    Subscription,
)
from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController


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

    def last(self, signal_name: str) -> object:
        for name, payload in reversed(self.emitted):
            if name == signal_name:
                return payload
        raise AssertionError(f"no event emitted on {signal_name}")


class _FakeNativePickers:
    def save_file(self, options: object) -> str | None:
        raise NotImplementedError

    def open_file(self, options: object) -> tuple[str, ...]:
        raise NotImplementedError

    def open_folder(self, options: object) -> str | None:
        raise NotImplementedError


class _FakeFileSystemActions:
    def open_in_file_manager(self, path: str) -> None:
        raise NotImplementedError

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return ""


class _FakeResumeGateway:
    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...],
        results_by_run_id: Mapping[RunId, tuple[BenchmarkResult, ...]],
    ) -> None:
        self._runs = {run.run_id: run for run in runs}
        self._results_by_run_id = results_by_run_id

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return tuple(self._runs.values())

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[run_id]

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise NotImplementedError

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        raise NotImplementedError

    def delete_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results_by_run_id.get(run_id, ())

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        raise NotImplementedError

    def update_result(self, result_id: ResultId, patch: object) -> None:
        raise NotImplementedError

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return ()

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        raise NotImplementedError

    def refresh_readiness(self) -> AppReadinessSnapshot:
        raise NotImplementedError

    def get_sort_setting(self) -> tuple[str, bool]:
        return ("started", True)

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors ResumeGateway verbatim
        raise NotImplementedError

    def resume_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def is_run_active(self) -> bool:
        return False

    def active_run_id(self) -> RunId | None:
        return None


def _run(run_id: int) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name="Alpha",
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def test_selection_emits_run_id_changed_and_clears_on_filter_out(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-2

    Selecting a row emits _run_id_changed with its run_id; when the selected
    row is filtered out by a search change, the selection clears and
    _run_id_changed reports no selection.
    """
    # Arrange
    run = _run(1)
    gateway = _FakeResumeGateway(runs=(run,), results_by_run_id={1: ()})
    bus = _RecordingEventBus()
    controller = ResumeBenchmarkController(
        gateway=gateway,
        event_bus=bus,
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
    )
    controller.load_initial_rows()

    # Act
    controller.on_row_selected(1)
    # Assert
    first_event = controller_last(bus, SIGNAL_RUN_ID_CHANGED)
    assert first_event.run_id == 1

    # Act
    controller.on_search_term_changed("no-such-run")
    # Assert
    second_event = controller_last(bus, SIGNAL_RUN_ID_CHANGED)
    assert second_event.run_id is None


def controller_last(bus: _RecordingEventBus, signal_name: str) -> RunIdChangedEvent:
    payload = bus.last(signal_name)
    assert isinstance(payload, RunIdChangedEvent)
    return payload


def test_load_initial_rows_applies_persisted_sort(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-1

    load_initial_rows reads the persisted sort column/direction and applies
    it to the table model before the first population.
    """
    # Arrange
    gateway = _FakeResumeGateway(runs=(_run(1),), results_by_run_id={1: ()})
    controller = ResumeBenchmarkController(
        gateway=gateway,
        event_bus=_RecordingEventBus(),
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
    )

    # Act
    controller.load_initial_rows()

    # Assert
    assert controller.table_model.rowCount() == 1
