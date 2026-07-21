"""Tests for ``DetachedChartWindow`` (STORY-064-AC-6).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §9
(detach to window).
"""

from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import ChartData, ChartKind, ChartSeries, RunMode
from ollama_llm_bench.backend.events import ChartDataChangedEvent
from ollama_llm_bench.ui.results._internal.charts_tab.controller import (
    ChartsTabController,
    ChartsTabViewProtocol,
)
from ollama_llm_bench.ui.results._internal.charts_tab.detached_window import (
    DetachedChartWindow,
    DetachedChartWindowConfig,
)
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.tests.conftest import FakeEventBus, FakeResultGateway, make_run

_VIEW_STATE_SETTING_KEY = "ui.result_view_state.charts.view_state.1"


def _populated(kind: ChartKind) -> ChartData:
    return ChartData(
        chart_kind=kind,
        categories=("Ollama Local / llama3",),
        series=(ChartSeries(name="v", values=(1.0,)),),
    )


def test_detached_window_forks_state_independently(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-064-AC-6

    Opening a detached chart window forks the parent tab's current filter/
    option state at open time; thereafter changing a filter in the detached
    window neither changes the parent controller's own view state nor writes
    anything to the per-run view-state store (charts_tab.md#9).
    """
    # Arrange -- the parent Charts tab, holding a populated run
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    for kind in (ChartKind.AVG_TTFT_PER_MODEL,):
        gateway.set_chart_data(1, kind, _populated(kind))
    parent = ChartsTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    parent_view = mocker.Mock(spec=ChartsTabViewProtocol)
    parent.bind(parent_view, on_drilldown=mocker.Mock())
    parent.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    forked_state = parent.current_view_state()
    persisted_before = gateway.get_setting(_VIEW_STATE_SETTING_KEY)

    # Act -- open a detached window forking the parent's current state
    window = DetachedChartWindow(
        config=DetachedChartWindowConfig(
            gateway=gateway,
            bus=FakeEventBus(),
            run_id=1,
            run_mode=RunMode.TASKS,
            initial_state=forked_state,
        )
    )
    qtbot.addWidget(window)
    # Act -- change a filter in the detached window only
    window.controller.on_filter_changed("statuses", ("completed",))

    # Assert -- the detached window's own state changed
    assert window.controller.current_view_state().filters_by_kind != forked_state.filters_by_kind
    # Assert -- the parent controller's state is untouched
    assert parent.current_view_state() == forked_state
    # Assert -- nothing new was persisted to the per-run view-state store
    assert gateway.get_setting(_VIEW_STATE_SETTING_KEY) == persisted_before


def test_detached_window_recomputes_on_chart_data_changed_for_its_own_run(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-064 (implementation_structure.md#5.3 subscription fix)

    The detached window's own ``ChartsTabController`` subscribes to
    ``_chart_data_changed`` -- owner-bound to the dialog itself (charts_tab.md#9,
    not to its inner ``ChartsTabView``) -- so publishing the event for the
    window's run triggers a fresh recompute.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    gateway.set_chart_data(
        1, ChartKind.AVG_TTFT_PER_MODEL, _populated(ChartKind.AVG_TTFT_PER_MODEL)
    )
    parent = ChartsTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    parent.bind(mocker.Mock(spec=ChartsTabViewProtocol), on_drilldown=mocker.Mock())
    parent.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    window = DetachedChartWindow(
        config=DetachedChartWindowConfig(
            gateway=gateway,
            bus=bus,
            run_id=1,
            run_mode=RunMode.TASKS,
            initial_state=parent.current_view_state(),
        )
    )
    qtbot.addWidget(window)
    recompute_spy = mocker.spy(window.controller, "recompute_and_push")
    # Act
    bus.emit(
        "_chart_data_changed",
        ChartDataChangedEvent(run_id=1, chart_kind=ChartKind.AVG_TTFT_PER_MODEL.value, revision=2),
    )
    # Assert
    recompute_spy.assert_called_once()


def test_detached_window_survives_independently_of_the_parent(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-064-AC-6 (EC-WS-1 adjacent)

    A detached chart window is a genuine top-level ``QDialog`` -- modeless,
    with no parent-owned lifetime tie that a workspace switch could sever.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    gateway.set_chart_data(
        1, ChartKind.AVG_TTFT_PER_MODEL, _populated(ChartKind.AVG_TTFT_PER_MODEL)
    )
    parent = ChartsTabController(
        gateway=gateway, bus=FakeEventBus(), view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    parent.bind(mocker.Mock(spec=ChartsTabViewProtocol), on_drilldown=mocker.Mock())
    parent.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    # Act
    window = DetachedChartWindow(
        config=DetachedChartWindowConfig(
            gateway=gateway,
            bus=FakeEventBus(),
            run_id=1,
            run_mode=RunMode.TASKS,
            initial_state=parent.current_view_state(),
        )
    )
    qtbot.addWidget(window)
    # Assert
    assert window.isModal() is False
    assert window.parent() is None
