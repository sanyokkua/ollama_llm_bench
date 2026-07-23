"""Colocated Resume-admission tests (STORY-074, EC-RUN-1a)."""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QTableView
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    InferenceActivity,
    InferenceActivityContext,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.backend.stores.inference_activity import (
    InferenceActivityStore,
    make_inference_activity_store,
)
from ollama_llm_bench.ui.resume_benchmark import make_resume_benchmark_widget
from ollama_llm_bench.ui.resume_benchmark.models import ResumeBenchmarkCollaborators

if TYPE_CHECKING:
    from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import RunTableModel

_RUN_ID: RunId = 1
_STUCK_RESULT_ID: ResultId = 1
_RETRY_RESULT_ID: ResultId = 2


class _FixedClock:
    """A deterministic ``Clock`` stand-in for the real ``InferenceActivityStore``."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


class _NoopSubscription:
    def cancel(self) -> None:
        return None


class _RecordingEventBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))


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

    def open_url(self, url: str) -> None:
        raise NotImplementedError

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return ""

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
    """A structural ``ResumeGateway`` fake (mirrors ``test_controller.py``'s inline fake)."""

    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...],
        results_by_run_id: Mapping[RunId, tuple[BenchmarkResult, ...]],
    ) -> None:
        self._runs = {run.run_id: run for run in runs}
        self._results_by_run_id = results_by_run_id
        self.set_sort_calls: list[tuple[str, bool]] = []
        self.drift_warnings_by_run_id: dict[RunId, tuple[DriftWarning, ...]] = {}

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
        self.set_sort_calls.append((column, descending))

    def resume_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def is_run_active(self) -> bool:
        return False

    def active_run_id(self) -> RunId | None:
        return None

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return self.drift_warnings_by_run_id.get(run_id, ())

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        raise NotImplementedError


class _FakeExportFilenameHelper:
    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        return f"Run_{run.run_id}_{kind}.{ext}"


class _AdmissionRecordingResumeGateway(_FakeResumeGateway):
    """``resume_run`` performs the production gate-first admission contract
    (mirrors ``BenchmarkFlowApi.resume``): a held gate makes the call a
    silent complete no-op; the stuck-row reset (rows still
    ``RUNNING_INFERENCE``) happens only after the gate is successfully
    acquired -- never by a call that was rejected.
    """

    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...],
        results_by_run_id: Mapping[RunId, tuple[BenchmarkResult, ...]],
        gate: InferenceActivityStore,
        rows: dict[ResultId, ResultStatus],
    ) -> None:
        super().__init__(runs=runs, results_by_run_id=results_by_run_id)
        self._gate = gate
        self.rows = rows
        self.reset_calls: list[tuple[ResultId, ...]] = []
        self.reset_returns: list[int] = []
        self.post_gate_stuck_resets: list[tuple[ResultId, ...]] = []
        self.resumed: list[RunId] = []
        self.rejected: list[RunId] = []

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        # Mirrors `list_resumable_results` (PENDING + retryable-failure rows
        # only) -- a RUNNING_INFERENCE row is never resumable; it only ever
        # reaches PENDING through the post-gate stuck-row reset inside
        # `resume_run` below.
        return tuple(
            r for r in self.list_results(run_id) if r.status is not ResultStatus.RUNNING_INFERENCE
        )

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        self.reset_calls.append(result_ids)
        changed = sum(1 for rid in result_ids if self.rows[rid] is not ResultStatus.PENDING)
        for rid in result_ids:
            self.rows[rid] = ResultStatus.PENDING
        self.reset_returns.append(changed)
        return changed

    def resume_run(self, run_id: RunId) -> None:
        lease = self._gate.try_acquire(
            InferenceActivity.BENCHMARK_RUN,
            InferenceActivityContext(
                activity=InferenceActivity.BENCHMARK_RUN, started_at=0, run_id=run_id
            ),
        )
        if lease is None:
            self.rejected.append(run_id)
            return
        stuck = tuple(
            rid for rid, status in self.rows.items() if status is ResultStatus.RUNNING_INFERENCE
        )
        if stuck:
            self.post_gate_stuck_resets.append(stuck)
            for rid in stuck:
                self.rows[rid] = ResultStatus.PENDING
        self.resumed.append(run_id)


def _run(run_id: RunId, *, run_name: str = "Alpha") -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=2,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _result(result_id: ResultId, status: ResultStatus) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=_RUN_ID,
        task_id=f"task-{result_id}",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _confirm_resume_summary_dialog(qtbot: QtBot) -> None:
    """Find the modal Resume Summary dialog opened by Resume Run and click its own Resume button."""
    dialog = cast("QDialog", QApplication.activeModalWidget())
    resume_button = cast(
        "QPushButton",
        dialog.findChild(QPushButton, "common_dialogs.resume_summary.resume_button"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        resume_button, Qt.MouseButton.LeftButton
    )


def test_double_resume_admission_is_a_noop_and_reset_is_idempotent(qtbot: QtBot) -> None:
    """Proves: STORY-074-AC-2

    Two Resume admissions racing the gate: the first acquires
    BENCHMARK_RUN and proceeds -- including the post-gate reset of the row
    still stuck ``RUNNING_INFERENCE`` -- and the second is a complete
    no-op. The stuck-row reset happens exactly once, only after the gate
    is held (never by the rejected call), and the retry-row reset is
    idempotent across the two confirms: the second reset changes zero
    rows, and every row ends up ``PENDING``.
    """
    # Arrange -- one RUNNING_INFERENCE (stuck) row and one FAILED_PROVIDER
    # (retryable) row on an INCOMPLETE run; a real gate wired over a
    # deterministic clock and a non-delivering recording event bus.
    run = _run(_RUN_ID)
    stuck_result = _result(_STUCK_RESULT_ID, ResultStatus.RUNNING_INFERENCE)
    retry_result = _result(_RETRY_RESULT_ID, ResultStatus.FAILED_PROVIDER)
    rows: dict[ResultId, ResultStatus] = {
        _STUCK_RESULT_ID: ResultStatus.RUNNING_INFERENCE,
        _RETRY_RESULT_ID: ResultStatus.FAILED_PROVIDER,
    }
    gate = make_inference_activity_store(clock=_FixedClock(), event_bus=_RecordingEventBus())
    gateway = _AdmissionRecordingResumeGateway(
        runs=(run,),
        results_by_run_id={_RUN_ID: (stuck_result, retry_result)},
        gate=gate,
        rows=rows,
    )
    collaborators = ResumeBenchmarkCollaborators(
        gateway=gateway,
        event_bus=_RecordingEventBus(),
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
        export_filenames=_FakeExportFilenameHelper(),
    )
    widget = make_resume_benchmark_widget(collaborators=collaborators)
    qtbot.addWidget(widget)
    widget.show()
    table_view = cast("QTableView", widget.findChild(QTableView, "resume_benchmark.table"))
    model = cast("RunTableModel", table_view.model())
    table_view.selectionModel().select(
        model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    resume_button = cast(
        "QPushButton", widget.findChild(QPushButton, "resume_benchmark.resume_button")
    )
    assert resume_button.isEnabled()

    # Act -- first admission via the widget: select the run, click Resume
    # Run, and confirm the Resume Summary dialog (its pre-checked
    # retryable row is reset, then the dialog calls
    # gateway.resume_run(...)), which acquires the real gate and performs
    # the post-gate stuck-row reset.
    QTimer.singleShot(0, lambda: _confirm_resume_summary_dialog(qtbot))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        resume_button, Qt.MouseButton.LeftButton
    )
    assert gateway.resumed == [_RUN_ID]

    # Act -- second admission, fired directly at the gateway seam this EC
    # names ("the Resume-Summary Confirm racing another resume path"): a
    # second Resume-Summary confirm would reset the same checked retryable
    # row and then call resume_run again, so this drives that exact
    # two-call sequence straight at the gateway -- the real admission race
    # the gate arbitrates, without a second nested-modal interaction.
    gateway.reset_results((_RETRY_RESULT_ID,))
    gateway.resume_run(_RUN_ID)

    # Assert -- admission arbitration: the first call acquired the gate
    # and proceeded, the second was rejected; the real gate still holds
    # BENCHMARK_RUN (never released by either call).
    assert gateway.resumed == [_RUN_ID]
    assert gateway.rejected == [_RUN_ID]
    assert gate.state().current is InferenceActivity.BENCHMARK_RUN
    # Assert -- the stuck-row reset happened exactly once, only after the
    # successful acquire (never by the rejected call).
    assert len(gateway.post_gate_stuck_resets) == 1
    # Assert -- the retry-row reset is idempotent across the two confirms:
    # the second call changed zero rows.
    assert gateway.reset_calls == [(_RETRY_RESULT_ID,), (_RETRY_RESULT_ID,)]
    assert gateway.reset_returns[-1] == 0
    # Assert -- every row ended up PENDING regardless of which admission
    # reset it.
    assert all(status is ResultStatus.PENDING for status in gateway.rows.values())
