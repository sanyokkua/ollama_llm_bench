"""``pytest-qt`` tests for the Summary tab mounted inside the Result widget
(STORY-062) -- AC-2 (mode-aware column offering), AC-5 (export mirrors the
tab), the construction/interaction smoke test, and the empty/partial/
populated render states.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QTableView, QWidget
import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    Difficulty,
    RequiredTerms,
    ResultStatus,
    RunId,
    RunMode,
    TaskOrigin,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_SUMMARY_DATA_CHANGED,
    SummaryDataChangedEvent,
)
from ollama_llm_bench.ui.results import make_result_widget
from ollama_llm_bench.ui.results._internal.summary_tab.controller import SummaryTabController
from ollama_llm_bench.ui.results._internal.summary_tab.select import (
    SummaryColumnKey,
    default_view_state,
)
from ollama_llm_bench.ui.results._internal.summary_tab.view import SummaryTabView
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ResultCollaborators
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

_GRADING_COLUMNS = frozenset(
    {
        SummaryColumnKey.PASS_RATE,
        SummaryColumnKey.COSINE_SCORE,
        SummaryColumnKey.JUDGE_PASS,
        SummaryColumnKey.JUDGE_FAIL,
        SummaryColumnKey.LAYER_MIX,
    }
)
_COMMON_COLUMNS = frozenset(
    {
        SummaryColumnKey.PROVIDER_MODEL,
        SummaryColumnKey.TASKS,
        SummaryColumnKey.AVG_TIME_S,
        SummaryColumnKey.AVG_TPS,
    }
)
_MULTI_ROW_GATEWAY_ROW_COUNT = 2


class _TaskAwareResultGateway(FakeResultGateway):
    """Extends the shared ``FakeResultGateway`` with a settable task list --
    the base fake always returns an empty tuple from ``list_tasks``, which is
    enough for STORY-061's shell but not for the Summary tab's aggregation,
    which looks up every result's task by id."""

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


class _CountingResultGateway(_TaskAwareResultGateway):
    """Counts ``list_results`` calls -- proves a debounced recompute runs
    exactly once, rather than merely asserting on rendered output."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]  # forwarded kwargs
        self.list_results_calls = 0

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        self.list_results_calls += 1
        return super().list_results(run_id)


def _make_multi_row_gateway() -> _TaskAwareResultGateway:
    """Two groups (distinct providers), one ``easy`` and one ``hard`` task --
    enough variety to exercise the filter chips and column controls."""
    task_easy = _task(task_id="task-easy")
    task_hard = BenchmarkTask(
        task_id="task-hard",
        task_origin=TaskOrigin.FILE,
        question="What is the tallest mountain?",
        category="geography",
        difficulty=Difficulty.HARD,
        required_terms=RequiredTerms(),
    )
    result_a = _result(1, task_id="task-easy", status=ResultStatus.COMPLETED)
    result_b = BenchmarkResult(
        result_id=2,
        run_id=1,
        task_id="task-hard",
        provider_id="22222222-2222-4222-8222-222222222222",
        provider_name="Other Provider",
        model_name="other-model",
        status=ResultStatus.COMPLETED,
        created_at="2024-01-01T00:00:00+00:00",
    )
    return _TaskAwareResultGateway(
        results_by_run_id={1: (result_a, result_b)}, tasks=(task_easy, task_hard)
    )


def _completed_result(run_id: RunId, *, task_id: str = "task-1") -> BenchmarkResult:
    return _result(run_id, task_id=task_id, status=ResultStatus.COMPLETED)


def _running_result(run_id: RunId, *, task_id: str = "task-1") -> BenchmarkResult:
    return _result(run_id, task_id=task_id, status=ResultStatus.RUNNING_INFERENCE)


def _result(run_id: RunId, *, task_id: str, status: ResultStatus) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=1,
        run_id=run_id,
        task_id=task_id,
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _task(*, task_id: str = "task-1") -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        question="What is the capital of France?",
        difficulty=Difficulty.MEDIUM,
        required_terms=RequiredTerms(),
    )


def _make_collaborators(gateway: FakeResultGateway, bus: FakeEventBus) -> ResultCollaborators:
    return ResultCollaborators(
        bus=bus,
        gateway=gateway,
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
    )


def _make_summary_tab(
    gateway: FakeResultGateway, bus: FakeEventBus
) -> tuple[SummaryTabView, SummaryTabController]:
    controller = SummaryTabController(
        gateway=gateway, bus=bus, view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    view = SummaryTabView()
    view.bind_controller(controller)
    controller.bind(view)
    return view, controller


@contextmanager
def _isolated_structlog_defaults() -> Iterator[None]:
    """Snapshot and restore ``structlog``'s process-global configuration.

    Mirrors ``ui/main_window/_internal/tests/test_shell.py``'s helper of the
    same name: ``structlog.testing.capture_logs()`` only swaps the processor
    chain, never ``wrapper_class``. If an earlier test in the full suite
    already called ``configure_logging(...)`` (which installs a
    process-global ``INFO``-filtering ``wrapper_class`` with no teardown),
    every ``DEBUG``-level call becomes a silent no-op regardless of
    ``capture_logs()`` -- making this test's DEBUG-event assertions depend
    on execution order across module boundaries.
    """
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.configure(**original_config)


# ---------------------------------------------------------------------------
# STORY-062-AC-2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("run_mode", "expect_grading_columns"),
    [
        (RunMode.SYNTHETIC, False),
        (RunMode.TASKS, False),
        (RunMode.GRADED, True),
    ],
    ids=["synthetic", "tasks", "graded"],
)
def test_offered_columns_per_mode(*, run_mode: RunMode, expect_grading_columns: bool) -> None:
    """Proves: STORY-062-AC-2

    For each run mode, the ``SummaryTabController``'s current column layout
    offers the grading-only column group solely for ``GRADED`` while always
    offering the common Provider/Model/Tasks/timing/throughput group --
    checked through the controller's own ``current_view_state`` property,
    not by reaching into gateway settings-string internals.
    """
    # Arrange
    gateway = FakeResultGateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    # Act
    with structlog.testing.capture_logs() as logs:
        controller.set_run_context(run_id=1, run_mode=run_mode)
    # Assert
    state = controller.current_view_state
    assert state is not None
    order = set(state.layout.order)
    assert order >= _COMMON_COLUMNS
    assert _GRADING_COLUMNS.issubset(order) is expect_grading_columns
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


# ---------------------------------------------------------------------------
# STORY-062-AC-5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("button_label", "expected_fmt"),
    [("Export CSV", "csv"), ("Export Markdown", "md")],
    ids=["csv", "markdown"],
)
def test_export_mirrors_visible_rows(qtbot: QtBot, *, button_label: str, expected_fmt: str) -> None:
    """Proves: STORY-062-AC-5

    Exporting CSV or Markdown while the Summary tab is the active tab
    invokes ``ResultGateway.serialize_table`` for the ``"summary"`` table --
    the export mirrors exactly the tab's current state, not a re-derived
    payload. The export button is only enabled once at least one result row
    is ``COMPLETED`` (``FooterController._has_completed_results``).
    """
    # Arrange
    gateway = _TaskAwareResultGateway(
        runs=(make_run(1, run_mode=RunMode.GRADED),),
        results_by_run_id={1: (_completed_result(1),)},
        tasks=(_task(),),
    )
    widget = make_result_widget(collaborators=_make_collaborators(gateway, FakeEventBus()))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.wait(0)
    slug = button_label.replace(" ", "_").lower()
    export_button = cast(
        "QPushButton", widget.findChild(QPushButton, f"result_widget.export.{slug}")
    )
    assert export_button.isEnabled()
    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        export_button, Qt.MouseButton.LeftButton
    )
    # Assert
    assert gateway.serialize_table_calls == [(1, "summary", expected_fmt)]


# ---------------------------------------------------------------------------
# Construction/interaction smoke test
# ---------------------------------------------------------------------------


def test_summary_tab_constructs_with_debug_lifecycle_events_and_no_errors(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Constructing and showing the Result widget mounts the Summary tab with
    zero ERROR/CRITICAL ``structlog`` records, and its DEBUG-level
    construction/bind lifecycle events are present in the captured log.
    """
    # Arrange
    gateway = _TaskAwareResultGateway(
        runs=(make_run(1, run_mode=RunMode.GRADED),),
        results_by_run_id={1: (_completed_result(1),)},
        tasks=(_task(),),
    )
    collaborators = _make_collaborators(gateway, FakeEventBus())
    # Act
    with _isolated_structlog_defaults(), structlog.testing.capture_logs() as logs:
        widget = make_result_widget(collaborators=collaborators)
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)
    # Assert
    event_names = {entry["event"] for entry in logs}
    assert widget.isVisible()
    assert "summary_tab_controller_constructed" in event_names
    assert "summary_tab_controller_bound" in event_names
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


# ---------------------------------------------------------------------------
# Empty / partial / populated render states
# ---------------------------------------------------------------------------


def test_summary_tab_shows_no_run_state_before_a_run_is_selected(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Before any run is selected, the Summary tab shows only the "select a
    run" message -- no filter bar, no table.
    """
    # Arrange
    view, controller = _make_summary_tab(FakeResultGateway(), FakeEventBus())
    qtbot.addWidget(view)
    # Act
    controller.set_run_context(run_id=None, run_mode=None)
    # Assert
    empty_label = cast("QLabel", view.findChild(QLabel, "summary_tab.empty_message"))
    filter_bar = cast("QWidget", view.findChild(QWidget, "summary_tab.filter_bar"))
    assert empty_label.text() == "Select a run to view its summary."
    assert filter_bar.isVisible() is False


def test_summary_tab_shows_partial_state_with_zero_completed_results(qtbot: QtBot) -> None:
    """Proves: STORY-062

    A selected run with results but none yet ``COMPLETED`` shows the
    "aggregates will fill in" empty-state message while still rendering the
    filter bar and table shell.
    """
    # Arrange
    gateway = _TaskAwareResultGateway(
        results_by_run_id={1: (_running_result(1),)}, tasks=(_task(),)
    )
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    empty_label = cast("QLabel", view.findChild(QLabel, "summary_tab.empty_message"))
    filter_bar = cast("QWidget", view.findChild(QWidget, "summary_tab.filter_bar"))
    assert (
        empty_label.text() == "No completed results yet — aggregates will fill in as tasks finish."
    )
    assert filter_bar.isVisible() is True


def test_summary_tab_shows_populated_state_with_completed_result_row(qtbot: QtBot) -> None:
    """Proves: STORY-062

    A selected run with a surviving completed result renders exactly one
    table row and hides the empty-state message.
    """
    # Arrange
    gateway = _TaskAwareResultGateway(
        results_by_run_id={1: (_completed_result(1),)}, tasks=(_task(),)
    )
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    empty_label = cast("QLabel", view.findChild(QLabel, "summary_tab.empty_message"))
    model = table.model()
    assert model is not None
    assert model.rowCount() == 1
    assert empty_label.isVisible() is False


# ---------------------------------------------------------------------------
# Interaction coverage -- chips, columns, sort, debounced live recompute
# ---------------------------------------------------------------------------


def test_difficulty_chip_toggle_reaggregates_through_the_view(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Unchecking one option inside the Difficulty filter chip's own menu
    routes through the view's chip-changed signal into the controller,
    which re-aggregates and pushes the narrowed ``SummaryViewModel`` back to
    the view -- the full chip-interaction round trip, not just the pure
    aggregation function.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    model = table.model()
    assert model is not None
    assert model.rowCount() == _MULTI_ROW_GATEWAY_ROW_COUNT
    difficulty_chip = cast(
        "QPushButton", view.findChild(QPushButton, "summary_tab.chip.difficulty")
    )
    menu = difficulty_chip.menu()
    assert menu is not None
    hard_action = next(action for action in menu.actions() if action.text() == "hard")
    # Act -- uncheck "hard", excluding the hard-difficulty row's group
    hard_action.setChecked(False)
    # Assert
    assert model.rowCount() == 1


def test_clear_filters_button_resets_active_filters(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Clicking "Clear filters" after narrowing a chip restores every row and
    disables the button again.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    difficulty_chip = cast(
        "QPushButton", view.findChild(QPushButton, "summary_tab.chip.difficulty")
    )
    menu = difficulty_chip.menu()
    assert menu is not None
    hard_action = next(action for action in menu.actions() if action.text() == "hard")
    hard_action.setChecked(False)
    clear_button = cast("QPushButton", view.findChild(QPushButton, "summary_tab.clear_filters"))
    assert clear_button.isEnabled()
    table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    model = table.model()
    assert model is not None
    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        clear_button, Qt.MouseButton.LeftButton
    )
    # Assert
    assert model.rowCount() == _MULTI_ROW_GATEWAY_ROW_COUNT
    assert clear_button.isEnabled() is False


def test_columns_popover_toggle_and_reset(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Opening the Columns popover, toggling a non-pinned column checkbox, and
    clicking "Reset" route through the view into the controller's
    ``on_column_toggled``/``on_columns_reset_clicked`` and back out to the
    mode's default layout.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    columns_button = cast("QPushButton", view.findChild(QPushButton, "summary_tab.columns_button"))
    # Act -- open the popover
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        columns_button, Qt.MouseButton.LeftButton
    )
    popover = cast("QWidget", view.findChild(QWidget, "summary_tab.columns_popover"))
    checkboxes = cast("Iterable[QCheckBox]", popover.findChildren(QCheckBox))
    toggle_target = next(checkbox for checkbox in checkboxes if checkbox.isEnabled())
    # Act -- hide a non-pinned column
    toggle_target.setChecked(False)
    # Assert
    state = controller.current_view_state
    assert state is not None
    assert len(state.layout.visible) == len(default_view_state(RunMode.GRADED).layout.visible) - 1
    # Act -- Reset restores the mode's default visibility
    popover_buttons = cast("Iterable[QPushButton]", popover.findChildren(QPushButton))
    reset_button = next(button for button in popover_buttons if button.text() == "Reset")
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        reset_button, Qt.MouseButton.LeftButton
    )
    # Assert
    state_after_reset = controller.current_view_state
    assert state_after_reset is not None
    assert state_after_reset.layout.visible == default_view_state(RunMode.GRADED).layout.visible


def test_sort_header_click_cycles_ascending_descending_cleared(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Clicking a column header cycles its sort ascending, then descending,
    then cleared -- the full three-state cycle ``on_sort_header_clicked``
    drives through ``_next_sort``.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    header = table.horizontalHeader()
    # Act -- first click on the first column: ascending
    header.sectionClicked.emit(0)
    first_sort = controller.current_view_state.sort  # type: ignore[union-attr]  # set above
    # Act -- second click on the same column: descending
    header.sectionClicked.emit(0)
    second_sort = controller.current_view_state.sort  # type: ignore[union-attr]  # set above
    # Act -- third click on the same column: cleared
    header.sectionClicked.emit(0)
    third_sort = controller.current_view_state.sort  # type: ignore[union-attr]  # set above
    # Assert
    assert first_sort.descending is False
    assert second_sort.column == first_sort.column
    assert second_sort.descending is True
    assert third_sort.column is None


def test_columns_reordered_updates_layout_order() -> None:
    """Proves: STORY-062

    ``on_columns_reordered`` persists a new column order into the current
    view state, read back through ``current_view_state``.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    state = controller.current_view_state
    assert state is not None
    new_order = tuple(reversed(state.layout.order))
    # Act
    controller.on_columns_reordered(new_order)
    # Assert
    reordered_state = controller.current_view_state
    assert reordered_state is not None
    assert reordered_state.layout.order == new_order


def test_summary_data_changed_event_schedules_a_debounced_recompute(qtbot: QtBot) -> None:
    """Proves: STORY-062

    A ``_summary_data_changed`` event for the displayed run schedules the
    view's 500 ms debounce timer, which re-aggregates exactly once after it
    fires -- not once per event, and not synchronously inline.
    """
    # Arrange
    gateway = _CountingResultGateway(
        results_by_run_id={1: (_completed_result(1),)}, tasks=(_task(),)
    )
    bus = FakeEventBus()
    view, controller = _make_summary_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    calls_before = gateway.list_results_calls
    # Act
    bus.emit(
        SIGNAL_SUMMARY_DATA_CHANGED, SummaryDataChangedEvent(run_id=1, row_count=1, revision=1)
    )
    qtbot.wait(600)
    # Assert
    assert gateway.list_results_calls == calls_before + 1


@pytest.mark.parametrize(
    "payload",
    [object(), SummaryDataChangedEvent(run_id=999, row_count=1, revision=1)],
    ids=["wrong_payload_type", "different_run_id"],
)
def test_summary_data_changed_event_ignored_when_malformed_or_for_another_run(
    qtbot: QtBot, *, payload: object
) -> None:
    """Proves: STORY-062

    A ``_summary_data_changed`` payload of the wrong type, or naming a run
    other than the one currently displayed, is ignored -- no recompute is
    scheduled.
    """
    # Arrange
    gateway = _CountingResultGateway(
        results_by_run_id={1: (_completed_result(1),)}, tasks=(_task(),)
    )
    bus = FakeEventBus()
    view, controller = _make_summary_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    calls_before = gateway.list_results_calls
    # Act
    bus.emit(SIGNAL_SUMMARY_DATA_CHANGED, payload)
    qtbot.wait(600)
    # Assert
    assert gateway.list_results_calls == calls_before


def test_set_run_context_to_no_run_before_binding_a_view_is_a_noop() -> None:
    """Proves: STORY-062

    Calling ``set_run_context(run_id=None, ...)`` before a view is ever
    bound is a safe no-op -- there is no view to push a "select a run"
    message to yet.
    """
    # Arrange
    gateway = FakeResultGateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    # Act
    controller.set_run_context(run_id=None, run_mode=None)
    # Assert
    assert controller.current_view_state is None


def test_models_chip_toggle_removes_a_whole_group_row_and_normalizes_full_selection(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-062

    Unchecking one model option in the Models chip drives
    ``on_chip_changed("models", ...)`` through ``_normalize_models``,
    narrowing ``filters.models`` and removing that model's whole row;
    re-checking every model normalizes the filter back to ``None`` ("all").
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    table = cast("QTableView", view.findChild(QTableView, "summary_tab.table"))
    model = table.model()
    assert model is not None
    assert model.rowCount() == _MULTI_ROW_GATEWAY_ROW_COUNT
    models_chip = cast("QPushButton", view.findChild(QPushButton, "summary_tab.chip.models"))
    menu = models_chip.menu()
    assert menu is not None
    first_action = menu.actions()[0]
    # Act -- uncheck one model, narrowing the filter
    first_action.setChecked(False)
    # Assert
    state = controller.current_view_state
    assert state is not None
    assert model.rowCount() == _MULTI_ROW_GATEWAY_ROW_COUNT - 1
    assert state.filters.models is not None
    # Act -- re-check it, selecting every model again. `apply()` rebuilt the
    # menu's QAction objects on the previous toggle (`set_options` calls
    # `QMenu.clear()`), so the action must be re-fetched rather than reusing
    # the now-deleted C++ object.
    rebuilt_menu = models_chip.menu()
    assert rebuilt_menu is not None
    rebuilt_menu.actions()[0].setChecked(True)
    # Assert -- normalizes back to "all" (`None`)
    state_after = controller.current_view_state
    assert state_after is not None
    assert state_after.filters.models is None
    assert model.rowCount() == _MULTI_ROW_GATEWAY_ROW_COUNT


def test_category_chip_toggle_normalizes_full_selection(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Unchecking then re-checking every Category chip option exercises
    ``on_chip_changed("category", ...)`` through both branches of
    ``_normalize_categories``.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    category_chip = cast("QPushButton", view.findChild(QPushButton, "summary_tab.chip.category"))
    menu = category_chip.menu()
    assert menu is not None
    first_action = menu.actions()[0]
    # Act -- uncheck one category, narrowing the filter
    first_action.setChecked(False)
    # Assert
    state = controller.current_view_state
    assert state is not None
    assert state.filters.categories is not None
    # Act -- re-check it, selecting every category again. `apply()` rebuilt
    # the menu's QAction objects on the previous toggle (`set_options` calls
    # `QMenu.clear()`), so the action must be re-fetched rather than reusing
    # the now-deleted C++ object.
    rebuilt_menu = category_chip.menu()
    assert rebuilt_menu is not None
    rebuilt_menu.actions()[0].setChecked(True)
    # Assert -- normalizes back to "all" (`None`)
    state_after = controller.current_view_state
    assert state_after is not None
    assert state_after.filters.categories is None


def test_verdict_chip_toggle_narrows_filters_verdicts(qtbot: QtBot) -> None:
    """Proves: STORY-062

    Toggling the Verdict chip's own menu routes through
    ``on_chip_changed("verdict", ...)``, narrowing ``filters.verdicts``.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    view, controller = _make_summary_tab(gateway, FakeEventBus())
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    verdict_chip = cast("QPushButton", view.findChild(QPushButton, "summary_tab.chip.verdict"))
    menu = verdict_chip.menu()
    assert menu is not None
    ungraded_action = next(action for action in menu.actions() if action.text() == "ungraded")
    # Act
    ungraded_action.setChecked(False)
    # Assert
    state = controller.current_view_state
    assert state is not None
    assert "ungraded" not in state.filters.verdicts


def test_chip_changed_with_unknown_chip_name_is_a_noop() -> None:
    """Proves: STORY-062

    An unrecognised chip name is a defensive no-op -- the view state is
    left byte-for-byte untouched.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    state_before = controller.current_view_state
    # Act
    controller.on_chip_changed("unknown", frozenset())
    # Assert
    assert controller.current_view_state == state_before


def test_column_filter_changed_replaces_the_prior_entry_for_the_same_column() -> None:
    """Proves: STORY-062

    ``on_column_filter_changed`` replaces any prior entry for the same
    column rather than accumulating duplicate entries.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.on_column_filter_changed(SummaryColumnKey.FAILED, frozenset({"errored"}))
    controller.on_column_filter_changed(SummaryColumnKey.FAILED, frozenset({"failed_timeout"}))
    # Assert
    state = controller.current_view_state
    assert state is not None
    assert len(state.column_filters) == 1
    assert state.column_filters[0].selected_values == frozenset({"failed_timeout"})


def test_current_run_id_tracks_the_bound_run() -> None:
    """Proves: STORY-062

    ``current_run_id`` reflects the run currently loaded via
    ``set_run_context``.
    """
    # Arrange
    gateway = _make_multi_row_gateway()
    controller = SummaryTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    assert controller.current_run_id == 1
