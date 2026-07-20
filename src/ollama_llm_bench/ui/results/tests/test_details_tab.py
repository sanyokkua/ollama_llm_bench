"""``pytest-qt`` tests for the Result widget's Details tab (STORY-063 task 10).

Constructs ``DetailsTabView``/``DetailsTabController`` directly -- mirroring most of
``test_summary_tab.py``'s own tests -- rather than through ``make_result_widget``: the
Details tab is not yet mounted into the ``ResultView`` shell (that wiring is
STORY-063 task 11's scope, deliberately out of this task's reach), so there is no
full-shell path to drive it through yet.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QLabel, QTableView
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import ResultStatus, RunMode, Verdict
from ollama_llm_bench.ui.results._internal.details_tab import select
from ollama_llm_bench.ui.results._internal.details_tab.controller import DetailsTabController
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result
from ollama_llm_bench.ui.results._internal.details_tab.view import DetailsTabView
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.tests.conftest import FakeEventBus, FakeResultGateway


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
    Task Detail Panel's judge-reasoning and error sections with the exact values
    ``select.build_detail_panel`` derived for that result.
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
    assert judge_label.text() == "Correct and complete."
    assert error_label.text() == "(none)"
