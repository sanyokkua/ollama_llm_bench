"""``pytest-qt`` tests for the Result widget's Details tab (STORY-063 task 10, task 12).

Most tests construct ``DetailsTabView``/``DetailsTabController`` directly -- the
sub-controller's own tests need no parent shell. The AC-4 (chart drill-down) and AC-5
(export) tests below drive the mounted ``ResultController``/``make_result_widget``
directly, since STORY-063 task 11 mounted the Details tab into the ``ResultView``
shell and both ACs are properties of that parent-level wiring, not the sub-controller
in isolation.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTableView, QTabWidget
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkResultAttempt,
    BenchmarkRun,
    BenchmarkTask,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.ui.results import make_result_widget
from ollama_llm_bench.ui.results._internal.controller import ResultController
from ollama_llm_bench.ui.results._internal.details_tab import select
from ollama_llm_bench.ui.results._internal.details_tab.controller import DetailsTabController
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result, make_task
from ollama_llm_bench.ui.results._internal.details_tab.view import DetailsTabView
from ollama_llm_bench.ui.results._internal.view import ResultView
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest, ResultCollaborators
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


@contextmanager
def _isolated_structlog_defaults() -> Iterator[None]:
    """Snapshot and restore ``structlog``'s process-global configuration.

    Mirrors ``test_summary_tab.py``'s helper of the same name:
    ``structlog.testing.capture_logs()`` only swaps the processor chain, never
    ``wrapper_class``. If an earlier test already called ``configure_logging(...)``
    (which installs a process-global ``INFO``-filtering ``wrapper_class`` with no
    teardown), every ``DEBUG``-level call becomes a silent no-op regardless of
    ``capture_logs()`` -- making this test's log assertions depend on execution
    order across module boundaries.
    """
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.configure(**original_config)


def _make_details_tab(
    gateway: FakeResultGateway, bus: FakeEventBus
) -> tuple[DetailsTabView, DetailsTabController]:
    controller = DetailsTabController(
        gateway=gateway, bus=bus, view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    view = DetailsTabView()
    view.bind_controller(controller)
    controller.bind(view)
    return view, controller


def _header_index(table: QTableView, label: str) -> int:
    model = table.model()
    assert model is not None
    header = table.horizontalHeader()
    for column in range(model.columnCount()):
        if model.headerData(column, header.orientation()) == label:
            return column
    raise AssertionError(f"no column header {label!r} in the rendered table")


def test_status_verdict_badge_roles(qtbot: QtBot) -> None:
    """Proves: STORY-063-AC-2

    The Details table renders the Status and Verdict cells for a completed,
    failed-verdict result with exactly the text ``select.badge_role_for_status``/
    ``select.badge_role_for_verdict`` map to their respective colour roles --
    proving the correct badge role/text is wired to the correct column, not merely
    that the pure mapping functions are correct in isolation.
    """
    # Arrange
    gateway = FakeResultGateway()
    gateway.set_results(
        1, (make_result(result_id=1, status=ResultStatus.COMPLETED, verdict=Verdict.FAIL),)
    )
    bus = FakeEventBus()
    view, controller = _make_details_tab(gateway, bus)
    qtbot.addWidget(view)
    # Act
    with _isolated_structlog_defaults(), structlog.testing.capture_logs() as logs:
        controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    table = cast("QTableView", view.findChild(QTableView, "details_tab.table"))
    model = table.model()
    assert model is not None
    status_column = _header_index(table, select.column_label(select.DetailsColumnKey.STATUS))
    verdict_column = _header_index(table, select.column_label(select.DetailsColumnKey.VERDICT))
    status_text = model.index(0, status_column).data()
    verdict_text = model.index(0, verdict_column).data()
    assert status_text == ResultStatus.COMPLETED.value
    assert select.badge_role_for_status(ResultStatus.COMPLETED) == "success"
    assert verdict_text == "FAIL"
    assert select.badge_role_for_verdict(Verdict.FAIL) == "error"
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_task_detail_panel_renders_full_record(qtbot: QtBot) -> None:
    """Proves: STORY-063-AC-3

    Selecting a Details-table row for real -- driven through the table's own
    selection model, not a hand-constructed ``ResultDetailViewModel`` -- renders the
    Task Detail Panel's judge-reasoning, error, and attempts sections with the exact
    values ``select.build_detail_panel`` derived for that result. The attempts
    section must include each attempt's timeout budget alongside its outcome and
    duration (details_tab.md §9 section 8).
    """
    # Arrange
    gateway = FakeResultGateway()
    gateway.set_results(
        1,
        (
            make_result(
                result_id=1,
                task_id="task-1",
                status=ResultStatus.COMPLETED,
                judge_reasoning="Correct and complete.",
                error_message=None,
                attempts=(
                    BenchmarkResultAttempt(
                        attempt_index=1,
                        timeout_ms=45_000,
                        duration_ms=1_200,
                        outcome=AttemptOutcome.SUCCESS,
                    ),
                ),
            ),
        ),
    )
    bus = FakeEventBus()
    view, controller = _make_details_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    table = cast("QTableView", view.findChild(QTableView, "details_tab.table"))
    model = table.model()
    assert model is not None
    selection_model = table.selectionModel()
    assert selection_model is not None
    # Act -- select the row for real, through the table's own selection model
    selection_model.setCurrentIndex(
        model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    # Assert
    judge_label = cast("QLabel", view.findChild(QLabel, "details_tab.detail_panel.judge_reasoning"))
    error_label = cast("QLabel", view.findChild(QLabel, "details_tab.detail_panel.error"))
    attempts_label = cast("QLabel", view.findChild(QLabel, "details_tab.detail_panel.attempts"))
    assert judge_label.text() == "Correct and complete."
    assert error_label.text() == "(none)"
    assert "timeout 45000 ms" in attempts_label.text()
    assert "duration 1200 ms" in attempts_label.text()


class _TaskAwareResultGateway(FakeResultGateway):
    """Extends the shared ``FakeResultGateway`` with a settable task list --
    mirrors ``test_summary_tab.py``'s own fake of the same name: the base fake
    always returns an empty tuple from ``list_tasks``, which is not enough for
    the parent shell's Summary sub-controller, which the mounted ``ResultController``
    always drives alongside the Details tab and which looks up every result's task
    by id."""

    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...] = (),
        results_by_run_id: dict[RunId, tuple[BenchmarkResult, ...]] | None = None,
        tasks: tuple[BenchmarkTask, ...] = (),
    ) -> None:
        super().__init__(runs=runs, results_by_run_id=results_by_run_id)
        self._tasks = tasks

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return self._tasks


def _make_result_collaborators(
    gateway: FakeResultGateway, bus: FakeEventBus
) -> ResultCollaborators:
    return ResultCollaborators(
        bus=bus,
        gateway=gateway,
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
    )


def test_chart_drilldown_applies_and_persists_filter(qtbot: QtBot) -> None:
    """Proves: STORY-063-AC-4

    A chart-click drill-down request delivered to the mounted ``ResultController``
    narrows the Details tab's active filters to the requested task, selects the
    matching row, switches the parent shell's active tab to Details, and persists
    the narrowed view state through ``PerRunViewStateStore`` -- not merely held in
    the sub-controller's memory.
    """
    # Arrange
    run = make_run(1, run_mode=RunMode.GRADED)
    result_a = make_result(result_id=1, task_id="task-1")
    result_b = make_result(result_id=2, task_id="task-2")
    gateway = _TaskAwareResultGateway(
        runs=(run,),
        results_by_run_id={1: (result_a, result_b)},
        tasks=(make_task(task_id="task-1"), make_task(task_id="task-2")),
    )
    controller = ResultController(collaborators=_make_result_collaborators(gateway, FakeEventBus()))
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    request = ChartDrilldownRequest(provider_id="prov-a", model_name="llama3", task_id="task-1")
    # Act
    controller.apply_chart_drilldown(request)
    # Assert -- the Details sub-controller's in-memory filter narrowed to the task
    view_state = controller._details_tab.current_view_state
    assert view_state is not None
    assert view_state.filters.tasks == ("task-1",)
    assert controller._details_tab._selected_result_id == 1
    # Assert -- the active tab really switched, observed through the mounted view
    tab_widget = cast("QTabWidget", view.findChild(QTabWidget, "result_widget.tabs"))
    assert tab_widget.currentIndex() == 1
    # Assert -- the narrowed filter was persisted, not just held in memory
    persisted_raw = gateway.get_setting("ui.result_view_state.details.view_state.1")
    assert persisted_raw is not None
    assert select.decode_view_state(persisted_raw).filters.tasks == ("task-1",)


def test_export_uses_details_table_when_details_tab_is_active(qtbot: QtBot) -> None:
    """Proves: STORY-063-AC-5

    Once the Details tab is the active tab, clicking the shared footer's Export CSV
    button invokes ``ResultGateway.serialize_table`` for the ``"details"`` table --
    the export mirrors whichever tab is actually on screen, matching the Summary
    tab's own ``table="summary"`` export contract (STORY-062-AC-5).
    """
    # Arrange
    run = make_run(1, status=RunStatus.COMPLETED)
    result = make_result(result_id=1, status=ResultStatus.COMPLETED)
    gateway = _TaskAwareResultGateway(
        runs=(run,), results_by_run_id={1: (result,)}, tasks=(make_task(),)
    )
    widget = make_result_widget(collaborators=_make_result_collaborators(gateway, FakeEventBus()))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.wait(0)
    tab_widget = cast("QTabWidget", widget.findChild(QTabWidget, "result_widget.tabs"))
    # Act -- switch to the Details tab; the footer rebuilds its export buttons on
    # every tab change, so the button must be re-fetched after switching (the prior
    # button's underlying C++ object is scheduled for deletion, mirroring
    # test_summary_tab.py's own re-fetch-after-rebuild pattern)
    tab_widget.setCurrentIndex(1)
    export_button = cast(
        "QPushButton", widget.findChild(QPushButton, "result_widget.export.export_csv")
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        export_button, Qt.MouseButton.LeftButton
    )
    # Assert
    assert gateway.serialize_table_calls == [(1, "details", "csv")]
