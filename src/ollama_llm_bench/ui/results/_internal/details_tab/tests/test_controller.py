"""Tests for ``DetailsTabController`` (STORY-063 task 8).

Drives the controller directly against a stub view object with recorded calls --
no Qt involved. Folded into a fuller ``test_details_tab.py`` in Task 10 once
``DetailsTabView`` exists.
"""

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.domain import ResultStatus, RunMode
from ollama_llm_bench.backend.events import DetailedDataChangedEvent
from ollama_llm_bench.ui.results._internal.details_tab.controller import (
    DetailsTabController,
    DetailsTabViewProtocol,
)
from ollama_llm_bench.ui.results._internal.details_tab.select import (
    DetailsChipDomains,
    DetailsColumnKey,
    default_view_state,
)
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result, make_task
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest
from ollama_llm_bench.ui.results.tests.conftest import FakeEventBus, FakeResultGateway

_SELECTED_RESULT_ID = 7


def _make_controller(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> DetailsTabController:
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    return DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )


def test_set_run_context_pushes_a_details_view_model(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1, status=ResultStatus.COMPLETED),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    view.apply.assert_called_once()
    domains = view.apply.call_args.kwargs["domains"]
    assert isinstance(domains, DetailsChipDomains)
    assert domains.statuses == (ResultStatus.COMPLETED,)


def test_get_column_filter_domain_reads_the_full_unfiltered_run(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063 review fix

    ``get_column_filter_domain`` must source its result from the gateway's current
    full result set -- not from any view-side filtered table -- so it always offers
    every distinct value regardless of any active filter (details_tab.md#6).
    """
    # Arrange
    fake_gateway.set_results(
        1,
        (
            make_result(result_id=1, status=ResultStatus.COMPLETED),
            make_result(result_id=2, status=ResultStatus.ERRORED),
        ),
    )
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    controller.on_column_filter_changed(DetailsColumnKey.STATUS, (ResultStatus.COMPLETED.value,))
    # Act
    domain = controller.get_column_filter_domain(DetailsColumnKey.STATUS)
    # Assert
    assert set(domain) == {ResultStatus.COMPLETED.value, ResultStatus.ERRORED.value}


def test_get_column_filter_domain_with_no_run_returns_empty(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063 review fix"""
    # Arrange
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    # Act
    domain = controller.get_column_filter_domain(DetailsColumnKey.STATUS)
    # Assert
    assert domain == ()


def test_set_run_context_with_no_run_applies_empty_state(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    # Act
    controller.set_run_context(run_id=None, run_mode=None)
    # Assert
    view.apply_no_run.assert_called_once()


def test_on_row_selected_pushes_a_detail_panel(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=_SELECTED_RESULT_ID),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.on_row_selected(_SELECTED_RESULT_ID)
    # Assert
    last_call = view.apply.call_args_list[-1]
    view_model = last_call.args[0]
    assert view_model.detail_panel is not None
    assert view_model.detail_panel.result_id == _SELECTED_RESULT_ID


def test_on_row_selected_with_a_result_id_absent_from_the_current_results_omits_the_panel(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A stale selection whose result no longer appears in the run's current results (e.g.
    after a live-data change) renders no Task Detail Panel rather than crashing."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    stale_result_id = 999
    # Act
    controller.on_row_selected(stale_result_id)
    # Assert
    last_call = view.apply.call_args_list[-1]
    view_model = last_call.args[0]
    assert view_model.selected_result_id == stale_result_id
    assert view_model.detail_panel is None


def test_apply_drilldown_filter_narrows_and_selects_matching_task(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(
        1, (make_result(result_id=1, task_id="task-a"), make_result(result_id=2, task_id="task-b"))
    )
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.apply_drilldown_filter(ChartDrilldownRequest(task_id="task-a"))
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.tasks == ("task-a",)


def test_set_run_terminal_state_enables_export(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    # Act
    controller.set_run_terminal_state(is_terminal=True)
    # Assert
    view.set_export_enabled.assert_called_once_with(enabled=True)


def test_detailed_data_changed_event_for_other_run_is_ignored(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    view.reset_mock()
    # Act
    fake_event_bus.emit(
        "_detailed_data_changed", DetailedDataChangedEvent(run_id=2, row_count=1, revision=1)
    )
    # Assert
    view.schedule_recompute.assert_not_called()


def test_on_chip_changed_updates_filters_and_recomputes(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(
        1, (make_result(result_id=1, task_id="task-a"), make_result(result_id=2, task_id="task-b"))
    )
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.on_chip_changed("tasks", ("task-a",))
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.tasks == ("task-a",)


def test_make_task_builder_available() -> None:
    """Proves: STORY-063 -- keeps make_task imported/used (fixture parity with select tests)."""
    # Arrange / Act
    task = make_task()
    # Assert
    assert task.task_id == "task-1"


# -- Coverage-closing tests: guard clauses and previously-unexercised branches --------------


def test_recompute_and_push_before_any_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A recompute request before ``bind``/``set_run_context`` ever ran does not crash."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.recompute_and_push()
    # Assert
    assert controller.current_view_state is None


def test_set_run_context_clears_run_without_a_bound_view(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Clearing the run before a view is ever bound skips the ``apply_no_run`` push."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.set_run_context(run_id=None, run_mode=None)
    # Assert
    assert controller.current_view_state is None


def test_on_chip_changed_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A chip change arriving before a run is selected leaves no view state to mutate."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_chip_changed("tasks", ("task-a",))
    # Assert
    assert controller.current_view_state is None


def test_on_chip_changed_with_unrecognised_chip_name_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A chip identifier outside the seven ``DetailsFilters`` fields leaves filters untouched."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    before = controller.current_view_state
    # Act
    controller.on_chip_changed("not_a_real_chip", ("x",))
    # Assert
    assert controller.current_view_state == before


def test_on_column_filter_changed_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A per-column filter change arriving before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_column_filter_changed(DetailsColumnKey.STATUS, ("completed",))
    # Assert
    assert controller.current_view_state is None


def test_on_clear_filters_clicked_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Clearing filters before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_clear_filters_clicked()
    # Assert
    assert controller.current_view_state is None


def test_on_clear_filters_clicked_resets_to_the_default_filters(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Given active chip filters, clearing them restores every chip to 'all selected'."""
    # Arrange
    fake_gateway.set_results(
        1, (make_result(result_id=1, task_id="task-a"), make_result(result_id=2, task_id="task-b"))
    )
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    controller.on_chip_changed("tasks", ("task-a",))
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.tasks == ("task-a",)
    # Act
    controller.on_clear_filters_clicked()
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.is_default()


def test_on_column_toggled_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A column-visibility toggle arriving before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_column_toggled(DetailsColumnKey.STATUS, visible=False)
    # Assert
    assert controller.current_view_state is None


def test_on_column_toggled_cannot_hide_the_pinned_provider_model_column(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """The pinned ``PROVIDER_MODEL`` column stays visible even when told to hide (§7)."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.on_column_toggled(DetailsColumnKey.PROVIDER_MODEL, visible=False)
    # Assert
    assert controller.current_view_state is not None
    assert DetailsColumnKey.PROVIDER_MODEL in controller.current_view_state.columns.visible


def test_on_column_toggled_hides_a_visible_column(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Toggling a currently-visible, non-pinned column off removes it from the visible set."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    assert DetailsColumnKey.STATUS in controller.current_view_state.columns.visible  # type: ignore[union-attr]
    # Act
    controller.on_column_toggled(DetailsColumnKey.STATUS, visible=False)
    # Assert
    assert controller.current_view_state is not None
    assert DetailsColumnKey.STATUS not in controller.current_view_state.columns.visible


def test_on_column_toggled_shows_a_hidden_column(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Toggling a currently-hidden column on adds it to the visible set."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    assert DetailsColumnKey.REASON not in controller.current_view_state.columns.visible  # type: ignore[union-attr]
    # Act
    controller.on_column_toggled(DetailsColumnKey.REASON, visible=True)
    # Assert
    assert controller.current_view_state is not None
    assert DetailsColumnKey.REASON in controller.current_view_state.columns.visible


def test_on_columns_reset_clicked_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Resetting columns before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_columns_reset_clicked()
    # Assert
    assert controller.current_view_state is None


def test_on_columns_reset_clicked_restores_the_mode_defaults(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Given a hidden column, resetting columns restores the run mode's default layout."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    controller.on_column_toggled(DetailsColumnKey.STATUS, visible=False)
    assert controller.current_view_state is not None
    assert DetailsColumnKey.STATUS not in controller.current_view_state.columns.visible
    # Act
    controller.on_columns_reset_clicked()
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.columns == default_view_state(RunMode.GRADED).columns


def test_on_columns_reordered_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A column-reorder arriving before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_columns_reordered((DetailsColumnKey.STATUS, DetailsColumnKey.PROVIDER_MODEL))
    # Assert
    assert controller.current_view_state is None


def test_on_columns_reordered_updates_the_column_order(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Given a drag-reorder, the new column order is stored verbatim."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    new_order = (DetailsColumnKey.STATUS, DetailsColumnKey.PROVIDER_MODEL, DetailsColumnKey.TASK)
    # Act
    controller.on_columns_reordered(new_order)
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.columns.order == new_order


def test_on_sort_header_clicked_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A sort-header click arriving before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.on_sort_header_clicked(DetailsColumnKey.STATUS)
    # Assert
    assert controller.current_view_state is None


def test_on_sort_header_clicked_on_a_new_column_sorts_ascending(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Clicking a column other than the current sort column starts it ascending."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)  # default sort is TIME_MS desc
    # Act
    controller.on_sort_header_clicked(DetailsColumnKey.STATUS)
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.sort.column == DetailsColumnKey.STATUS
    assert controller.current_view_state.sort.descending is False


def test_on_sort_header_clicked_twice_on_the_same_column_sorts_descending(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """Clicking the same ascending column again flips it to descending."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    controller.on_sort_header_clicked(DetailsColumnKey.STATUS)
    # Act
    controller.on_sort_header_clicked(DetailsColumnKey.STATUS)
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.sort.column == DetailsColumnKey.STATUS
    assert controller.current_view_state.sort.descending is True


def test_on_sort_header_clicked_a_third_time_clears_the_sort(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A third click on the already-descending column clears the sort entirely.

    The default view state's sort is TIME_MS descending, so a single click on
    TIME_MS -- the already-active, already-descending column -- exercises this
    same 'cleared' branch directly.
    """
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act -- TIME_MS is already the default sort column, descending
    controller.on_sort_header_clicked(DetailsColumnKey.TIME_MS)
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.sort.column is None
    assert controller.current_view_state.sort.descending is True


def test_apply_drilldown_filter_before_run_context_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A drill-down request arriving before a run is selected is a no-op."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act
    controller.apply_drilldown_filter(ChartDrilldownRequest(task_id="task-a"))
    # Assert
    assert controller.current_view_state is None


def test_apply_drilldown_filter_with_no_task_id_does_not_select_a_row(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A model-only drill-down narrows the filter but selects no row (no ``task_id``)."""
    # Arrange
    fake_gateway.set_results(
        1, (make_result(result_id=1, provider_id="prov-a", model_name="llama3"),)
    )
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.apply_drilldown_filter(
        ChartDrilldownRequest(provider_id="prov-a", model_name="llama3")
    )
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.models == (("prov-a", "llama3"),)
    last_view_model = view.apply.call_args.args[0]
    assert last_view_model.selected_result_id is None


def test_apply_drilldown_filter_with_unmatched_task_id_selects_no_row(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A drill-down task id absent from the run's current results narrows the filter but
    leaves the selection untouched -- there is no row to select."""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=1, task_id="task-a"),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.apply_drilldown_filter(ChartDrilldownRequest(task_id="task-does-not-exist"))
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.tasks == ("task-does-not-exist",)
    last_view_model = view.apply.call_args.args[0]
    assert last_view_model.selected_result_id is None


def test_set_run_terminal_state_disables_export(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A non-terminal run state disables the export action."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    # Act
    controller.set_run_terminal_state(is_terminal=False)
    # Assert
    view.set_export_enabled.assert_called_once_with(enabled=False)


def test_set_run_terminal_state_before_bind_is_noop(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """A terminal-state notification arriving before a view is bound does not crash."""
    # Arrange
    controller = _make_controller(fake_gateway, fake_event_bus)
    # Act / Assert -- no view is bound; this must not raise
    controller.set_run_terminal_state(is_terminal=True)


def test_current_run_id_reflects_the_active_run_context(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """The ``current_run_id`` property mirrors the run last set via ``set_run_context``."""
    # Arrange
    other_run_id = 3
    fake_gateway.set_results(other_run_id, (make_result(result_id=1, run_id=other_run_id),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    # Act
    controller.set_run_context(run_id=other_run_id, run_mode=RunMode.GRADED)
    # Assert
    assert controller.current_run_id == other_run_id


def test_detailed_data_changed_event_with_wrong_payload_type_is_ignored(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A payload of the wrong type on the ``_detailed_data_changed`` signal is ignored rather
    than crashing the handler."""
    # Arrange
    fake_gateway.set_results(1, (make_result(),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    view.reset_mock()
    # Act
    fake_event_bus.emit("_detailed_data_changed", object())
    # Assert
    view.schedule_recompute.assert_not_called()


def test_detailed_data_changed_event_for_current_run_schedules_a_recompute(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus, mocker: MockerFixture
) -> None:
    """A ``DetailedDataChangedEvent`` for the currently-shown run schedules a debounced
    recompute on the bound view rather than recomputing inline."""
    # Arrange
    fake_gateway.set_results(1, (make_result(),))
    controller = _make_controller(fake_gateway, fake_event_bus)
    view = mocker.Mock(spec=DetailsTabViewProtocol)
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    view.reset_mock()
    # Act
    fake_event_bus.emit(
        "_detailed_data_changed", DetailedDataChangedEvent(run_id=1, row_count=1, revision=2)
    )
    # Assert
    view.schedule_recompute.assert_called_once()
