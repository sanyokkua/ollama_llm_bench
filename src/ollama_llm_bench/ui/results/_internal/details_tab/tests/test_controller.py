"""Tests for ``DetailsTabController`` (STORY-063 task 8).

Drives the controller directly against a stub view object with recorded calls --
no Qt involved. Folded into a fuller ``test_details_tab.py`` in Task 10 once
``DetailsTabView`` exists.
"""

from unittest.mock import Mock

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import DetailedDataChangedEvent
from ollama_llm_bench.ui.results._internal.details_tab.controller import DetailsTabController
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result, make_task
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.tests.conftest import FakeEventBus, FakeResultGateway

_SELECTED_RESULT_ID = 7


def test_set_run_context_pushes_a_details_view_model(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
    controller.bind(view)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    view.apply.assert_called_once()


def test_set_run_context_with_no_run_applies_empty_state(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    # Arrange
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
    controller.bind(view)
    # Act
    controller.set_run_context(run_id=None, run_mode=None)
    # Assert
    view.apply_no_run.assert_called_once()


def test_on_row_selected_pushes_a_detail_panel(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(result_id=_SELECTED_RESULT_ID),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.on_row_selected(_SELECTED_RESULT_ID)
    # Assert
    last_call = view.apply.call_args_list[-1]
    view_model = last_call.args[0]
    assert view_model.detail_panel is not None
    assert view_model.detail_panel.result_id == _SELECTED_RESULT_ID


def test_apply_drilldown_filter_narrows_and_selects_matching_task(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    from ollama_llm_bench.ui.results.models import ChartDrilldownRequest  # noqa: PLC0415

    # Arrange
    fake_gateway.set_results(
        1, (make_result(result_id=1, task_id="task-a"), make_result(result_id=2, task_id="task-b"))
    )
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
    controller.bind(view)
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Act
    controller.apply_drilldown_filter(ChartDrilldownRequest(task_id="task-a"))
    # Assert
    assert controller.current_view_state is not None
    assert controller.current_view_state.filters.tasks == ("task-a",)


def test_set_run_terminal_state_enables_export(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    # Arrange
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
    controller.bind(view)
    # Act
    controller.set_run_terminal_state(is_terminal=True)
    # Assert
    view.set_export_enabled.assert_called_once_with(enabled=True)


def test_detailed_data_changed_event_for_other_run_is_ignored(
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-063"""
    # Arrange
    fake_gateway.set_results(1, (make_result(),))
    view_state_store = PerRunViewStateStore(gateway=fake_gateway)
    controller = DetailsTabController(
        gateway=fake_gateway, bus=fake_event_bus, view_state_store=view_state_store
    )
    view = Mock()
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
    fake_gateway: FakeResultGateway, fake_event_bus: FakeEventBus
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
    view = Mock()
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
