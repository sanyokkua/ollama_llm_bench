"""Tests for the Result widget's Charts tab (STORY-064).

Covers the pure logic (mode_policy, drilldown, view_state, painting smoke
tests) and the six acceptance criteria: the mode-offered chart set (AC-1),
non-wrapping navigation (AC-2), skip-empty navigation (AC-3), chart-click
drill-down routed through the parent controller (AC-4), the themed off-screen
export (AC-5, EC-RES-4). AC-6 (detached-window state forking) lives in
``test_detached_chart_window.py``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QTabWidget, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    ChartData,
    ChartKind,
    ChartSeries,
    HeatmapData,
    RunMode,
)
from ollama_llm_bench.backend.events import ChartDataChangedEvent
from ollama_llm_bench.ui.results._internal.charts_tab import drilldown, mode_policy, painting
from ollama_llm_bench.ui.results._internal.charts_tab.controller import (
    ChartsTabController,
    ChartsTabViewProtocol,
)
from ollama_llm_bench.ui.results._internal.charts_tab.view_state import (
    decode_view_state,
    default_view_state,
    encode_view_state,
)
from ollama_llm_bench.ui.results._internal.controller import ResultController
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result, make_task
from ollama_llm_bench.ui.results._internal.view import ResultView
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest, ResultCollaborators
from ollama_llm_bench.ui.results.tests.conftest import (
    FakeClipboard,
    FakeEventBus,
    FakeExportFilenameHelper,
    FakeFileSystemActions,
    FakeModelFetcher,
    FakeNativePickers,
    FakeNotificationService,
    FakeProviderListSource,
    FakeResultGateway,
    make_run,
)
from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens, resolve_color

_SKIP_LANDING_INDEX = 2

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@contextmanager
def _isolated_structlog_defaults() -> Iterator[None]:
    """Snapshot and restore ``structlog``'s process-global configuration.

    Mirrors ``test_summary_tab.py``'s/``test_details_tab.py``'s identical helper.
    """
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.configure(**original_config)


def _populated(kind: ChartKind, *, category: str = "Ollama Local / llama3") -> ChartData:
    return ChartData(
        chart_kind=kind, categories=(category,), series=(ChartSeries(name="v", values=(1.0,)),)
    )


def _empty(kind: ChartKind) -> ChartData:
    return ChartData(chart_kind=kind, categories=(), series=(), empty_state_message="No data yet.")


def _make_controller(
    gateway: FakeResultGateway, bus: FakeEventBus, mocker: MockerFixture
) -> tuple[ChartsTabController, MagicMock]:
    controller = ChartsTabController(
        gateway=gateway, bus=bus, view_state_store=PerRunViewStateStore(gateway=gateway)
    )
    view = mocker.Mock(spec=ChartsTabViewProtocol)
    controller.bind(view, on_drilldown=mocker.Mock())
    return controller, view


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
        provider_source=FakeProviderListSource(),
        model_fetcher=FakeModelFetcher(),
    )


# ---------------------------------------------------------------------------
# Pure logic: mode_policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("run_mode", "expected_count", "expects_grading_charts"),
    [
        (RunMode.SYNTHETIC, 6, False),
        (RunMode.TASKS, 6, False),
        (RunMode.GRADED, 12, True),
    ],
    ids=["synthetic", "tasks", "graded"],
)
def test_offered_chart_kinds_per_mode(
    *, run_mode: RunMode, expected_count: int, expects_grading_charts: bool
) -> None:
    """Proves: STORY-064-AC-1

    Pure ``mode_policy.offered_chart_kinds`` matches the mode-availability
    matrix (charts_tab.md#4): six charts for SYNTHETIC/TASKS, all twelve for
    GRADED, with the six grading-only kinds present only in GRADED.
    """
    # Act
    offered = mode_policy.offered_chart_kinds(run_mode)
    # Assert
    assert len(offered) == expected_count
    assert (ChartKind.PASS_RATE_BY_MODEL in offered) is expects_grading_charts
    assert (ChartKind.HEATMAP_TASK_BY_MODEL in offered) is expects_grading_charts


def test_next_navigable_index_skips_empty_and_stops_at_end() -> None:
    """Proves: STORY-064-AC-3 (pure-logic backbone)"""
    # Arrange
    offered = (
        ChartKind.AVG_TTFT_PER_MODEL,
        ChartKind.AVG_TPS_PER_MODEL,
        ChartKind.AVG_TIME_PER_MODEL,
    )
    has_data = {
        ChartKind.AVG_TTFT_PER_MODEL: True,
        ChartKind.AVG_TPS_PER_MODEL: False,
        ChartKind.AVG_TIME_PER_MODEL: True,
    }
    # Act
    landed = mode_policy.next_navigable_index(
        current_index=0, offered=offered, has_data=has_data.__getitem__
    )
    exhausted = mode_policy.next_navigable_index(
        current_index=_SKIP_LANDING_INDEX, offered=offered, has_data=has_data.__getitem__
    )
    # Assert -- skips index 1 (empty), lands on index 2; nothing left afterward
    assert landed == _SKIP_LANDING_INDEX
    assert exhausted is None


def test_prev_navigable_index_stops_at_start() -> None:
    """Proves: STORY-064-AC-2 (pure-logic backbone)"""
    # Arrange
    offered = (ChartKind.AVG_TTFT_PER_MODEL, ChartKind.AVG_TPS_PER_MODEL)
    has_data = {ChartKind.AVG_TTFT_PER_MODEL: True, ChartKind.AVG_TPS_PER_MODEL: True}
    # Act
    result = mode_policy.prev_navigable_index(
        current_index=0, offered=offered, has_data=has_data.__getitem__
    )
    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# Pure logic: drilldown
# ---------------------------------------------------------------------------


def test_map_bar_click_narrows_to_single_model() -> None:
    """Proves: STORY-064-AC-4 (pure-logic backbone)"""
    # Act
    request = drilldown.map_bar_click(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL, provider_id="prov-a", model_name="llama3"
    )
    # Assert
    assert request == ChartDrilldownRequest(provider_id="prov-a", model_name="llama3")


@pytest.mark.parametrize(
    ("chart_kind", "expected_field"),
    [
        (ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED, "status"),
        (ChartKind.VERDICT_COUNTS_STACKED, "verdict"),
    ],
)
def test_map_stacked_segment_click_narrows_by_status_or_verdict(
    *, chart_kind: ChartKind, expected_field: str
) -> None:
    """Proves: STORY-064-AC-4 (pure-logic backbone)"""
    # Act
    request = drilldown.map_stacked_segment_click(
        chart_kind=chart_kind, provider_id="prov-a", model_name="llama3", segment="completed"
    )
    # Assert
    assert getattr(request, expected_field) == "completed"


def test_map_heatmap_cell_click_narrows_to_task_and_model() -> None:
    """Proves: STORY-064-AC-4 (pure-logic backbone), chart 9"""
    # Act
    request = drilldown.map_heatmap_cell_click(
        provider_id="prov-a", model_name="llama3", task_id="task-1"
    )
    # Assert
    assert request == ChartDrilldownRequest(
        provider_id="prov-a", model_name="llama3", task_id="task-1"
    )


def test_map_grouped_bar_click_narrows_to_model_and_category() -> None:
    """Proves: STORY-064-AC-4 (pure-logic backbone), chart 10"""
    # Act
    request = drilldown.map_grouped_bar_click(
        provider_id="prov-a", model_name="llama3", category="reasoning"
    )
    # Assert
    assert request.category == "reasoning"


def test_map_scatter_point_click_ignores_task_id_for_speed_vs_quality() -> None:
    """Proves: STORY-064-AC-4 (pure-logic backbone), chart 11"""
    # Act
    request = drilldown.map_scatter_point_click(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        provider_id="prov-a",
        model_name="llama3",
        task_id="task-1",
    )
    # Assert
    assert request.task_id is None


# ---------------------------------------------------------------------------
# Pure logic: view_state
# ---------------------------------------------------------------------------


def test_default_view_state_seeds_first_offered_kind() -> None:
    """A fresh Charts view state seeds ``last_chart_kind`` to the run mode's
    first offered chart kind -- unit coverage for ``view_state.py``'s default
    factory, exercised separately from the export-theme acceptance criteria."""
    # Act
    state = default_view_state(RunMode.SYNTHETIC)
    # Assert
    assert state.last_chart_kind == ChartKind.AVG_TTFT_PER_MODEL
    assert state.outlier_exclusion is True
    assert state.filters_by_kind == {}
    assert state.hidden_series_by_kind == {}


def test_view_state_round_trips_through_encode_decode() -> None:
    # Arrange
    state = default_view_state(RunMode.GRADED)
    # Act
    decoded = decode_view_state(encode_view_state(state))
    # Assert
    assert decoded == state


# ---------------------------------------------------------------------------
# Pure logic / Qt smoke: painting
# ---------------------------------------------------------------------------


def test_draw_empty_state_paints_something(qtbot: QtBot) -> None:
    # Arrange
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    image = QImage(200, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    # Act
    painting.draw_empty_state(
        painter, rect=QRectF(0, 0, 200, 150), message="No data", tokens=tokens
    )
    painter.end()
    # Assert
    assert not image.allGray()


def test_render_chart_png_returns_png_bytes() -> None:
    # Arrange
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    data = _populated(ChartKind.AVG_TTFT_PER_MODEL)
    # Act
    payload = painting.render_chart_png(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL, data=data, tokens=tokens
    )
    # Assert
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_chart_svg_returns_svg_bytes() -> None:
    # Arrange
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    data = _populated(ChartKind.AVG_TTFT_PER_MODEL)
    # Act
    payload = painting.render_chart_svg(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL, data=data, tokens=tokens
    )
    # Assert
    assert b"<svg" in payload or b"<?xml" in payload


def test_draw_scatter_chart_applies_low_sample_hatch_to_flagged_points(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-064 (charts_tab.md#6.1 chart-11 low-sample hatch fix)

    A ``SPEED_VS_QUALITY_SCATTER`` point backed by a low sample size is drawn
    via ``draw_low_sample_hatch`` (the shared hatch/``n=N`` marker), not a
    plain ellipse -- matching the bar-chart/grouped-bar-chart low-sample
    contract already enforced for the other chart shapes (charts_tab.md#6.1).
    """
    # Arrange
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    data = ChartData(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        categories=("Ollama Local / llama3", "Ollama Local / mistral"),
        series=(
            ChartSeries(
                name="Tokens/sec",
                values=(10.0, 20.0),
                sample_sizes=(1, 5),
                low_sample_flags=(True, False),
            ),
            ChartSeries(
                name="Pass rate",
                values=(0.5, 0.9),
                sample_sizes=(1, 5),
                low_sample_flags=(True, False),
            ),
        ),
    )
    image = QImage(200, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    hatch_spy = mocker.spy(painting, "draw_low_sample_hatch")
    # Act
    painting.draw_scatter_chart(painter, rect=QRectF(0, 0, 200, 150), data=data, tokens=tokens)
    painter.end()
    # Assert
    assert hatch_spy.call_count == 1
    assert hatch_spy.call_args.kwargs["sample_size"] == 1


def test_draw_heatmap_paints_something() -> None:
    # Arrange
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    data = HeatmapData(row_labels=("t1",), column_labels=("m1",), cells=((1.0,),))
    image = QImage(200, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    # Act
    painting.draw_heatmap(painter, rect=QRectF(0, 0, 200, 150), data=data, tokens=tokens)
    painter.end()
    # Assert
    assert not image.allGray()


# ---------------------------------------------------------------------------
# STORY-064-AC-1: mode-offered chart set, at the controller level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("run_mode", "expected_kinds"),
    [
        (RunMode.SYNTHETIC, mode_policy.SIX_CHART_OFFERED_KINDS),
        (RunMode.TASKS, mode_policy.SIX_CHART_OFFERED_KINDS),
        (RunMode.GRADED, mode_policy.TWELVE_CHART_OFFERED_KINDS),
    ],
    ids=["synthetic", "tasks", "graded"],
)
def test_offered_chart_set_per_mode(
    mocker: MockerFixture, *, run_mode: RunMode, expected_kinds: tuple[ChartKind, ...]
) -> None:
    """Proves: STORY-064-AC-1

    For each run mode, the ``ChartsViewModel`` pushed by ``ChartsTabController``
    lists exactly the mode-offered chart kinds, in mode-offered order, in its
    ``dropdown_entries`` -- with no ERROR/CRITICAL log emitted.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=run_mode),))
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    # Act
    with _isolated_structlog_defaults(), structlog.testing.capture_logs() as logs:
        controller.set_run_context(run_id=1, run_mode=run_mode)
    # Assert
    view_model = view.apply.call_args.args[0]
    assert tuple(kind for kind, _label, _has_data in view_model.dropdown_entries) == expected_kinds
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


# ---------------------------------------------------------------------------
# STORY-064 spec-conformance fix: the missing ``_chart_data_changed`` subscription
# (implementation_structure.md#5.3)
# ---------------------------------------------------------------------------


def test_chart_data_changed_event_for_current_run_recomputes_and_pushes(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-064 (implementation_structure.md#5.3 subscription fix)

    A ``ChartDataChangedEvent`` for the currently-bound run recomputes and
    pushes a fresh ``ChartsViewModel`` to the bound view.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    controller, view = _make_controller(gateway, bus, mocker)
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    view.apply.reset_mock()
    # Act
    bus.emit(
        "_chart_data_changed",
        ChartDataChangedEvent(run_id=1, chart_kind=ChartKind.AVG_TTFT_PER_MODEL.value, revision=2),
    )
    # Assert
    view.apply.assert_called_once()


def test_chart_data_changed_event_for_other_run_is_ignored(mocker: MockerFixture) -> None:
    """Proves: STORY-064 (implementation_structure.md#5.3 subscription fix)

    A ``ChartDataChangedEvent`` for a run other than the currently-bound one
    is ignored -- no recompute, no push.
    """
    # Arrange
    bus = FakeEventBus()
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    controller, view = _make_controller(gateway, bus, mocker)
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    view.apply.reset_mock()
    # Act
    bus.emit(
        "_chart_data_changed",
        ChartDataChangedEvent(run_id=2, chart_kind=ChartKind.AVG_TTFT_PER_MODEL.value, revision=2),
    )
    # Assert
    view.apply.assert_not_called()


# ---------------------------------------------------------------------------
# STORY-064-AC-2: navigation does not wrap
# ---------------------------------------------------------------------------


def test_navigation_does_not_wrap(mocker: MockerFixture) -> None:
    """Proves: STORY-064-AC-2

    On the first mode-offered chart, prev is disabled; on the last, next is
    disabled -- navigation never wraps around the mode-offered set.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    for kind in mode_policy.SIX_CHART_OFFERED_KINDS:
        gateway.set_chart_data(1, kind, _populated(kind))
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    # Act -- first chart
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    # Assert
    first_vm = view.apply.call_args.args[0]
    assert first_vm.prev_enabled is False
    assert first_vm.next_enabled is True
    # Act -- step to the last chart
    for _ in range(len(mode_policy.SIX_CHART_OFFERED_KINDS) - 1):
        controller.on_next_clicked()
    last_vm = view.apply.call_args.args[0]
    # Assert
    assert last_vm.chart_kind == mode_policy.SIX_CHART_OFFERED_KINDS[-1]
    assert last_vm.next_enabled is False
    assert last_vm.prev_enabled is True


# ---------------------------------------------------------------------------
# STORY-064-AC-3: navigation skips offered-but-empty charts
# ---------------------------------------------------------------------------


def test_navigation_skips_empty_charts(mocker: MockerFixture) -> None:
    """Proves: STORY-064-AC-3

    An offered-but-empty chart between two populated charts is skipped by
    next-click navigation, but stays directly reachable from the dropdown.
    """
    # Arrange
    offered = mode_policy.SIX_CHART_OFFERED_KINDS
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    gateway.set_chart_data(1, offered[0], _populated(offered[0]))
    gateway.set_chart_data(1, offered[1], _empty(offered[1]))
    gateway.set_chart_data(1, offered[2], _populated(offered[2]))
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    # Act
    controller.on_next_clicked()
    # Assert -- landed on offered[2], skipping the empty offered[1]
    view_model = view.apply.call_args.args[0]
    assert view_model.chart_kind == offered[2]
    # Assert -- the empty chart still shows in the dropdown, marked no-data
    empty_entry = next(e for e in view_model.dropdown_entries if e[0] == offered[1])
    assert empty_entry[2] is False
    # Act -- still directly reachable from the dropdown
    controller.on_chart_kind_selected(offered[1])
    reselected_vm = view.apply.call_args.args[0]
    assert reselected_vm.chart_kind == offered[1]
    assert reselected_vm.empty_state_message is not None


# ---------------------------------------------------------------------------
# STORY-064 spec-conformance fixes: §11 empty states, §4.1 meta-line casing
# ---------------------------------------------------------------------------


def test_overall_empty_state_message_when_every_offered_chart_is_empty(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-064 (charts_tab.md#11 overall-empty fix)

    When every mode-offered chart is empty, the canvas shows the overall
    "Charts require at least one completed task." message rather than the
    active chart's own kind-specific empty message.
    """
    # Arrange -- no chart data configured; every offered kind defaults empty
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    # Assert
    view_model = view.apply.call_args.args[0]
    assert view_model.empty_state_message == "Charts require at least one completed task."


def test_grading_only_chart_kind_requested_outside_graded_mode_shows_defence_message(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-064 (charts_tab.md#11 GRADED-only defence-in-depth fix)

    A GRADED-only chart kind requested while the run is not GRADED -- e.g. a
    directly-set, stale persisted view state -- is defended in depth: the
    canvas shows "This chart is available only for graded runs." rather than
    crashing when the requested kind is absent from the mode-offered set.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    # Act -- force the active kind to a GRADED-only chart kind (defensive path)
    controller.on_chart_kind_selected(ChartKind.PASS_RATE_BY_MODEL)
    # Assert
    view_model = view.apply.call_args.args[0]
    assert view_model.empty_state_message == "This chart is available only for graded runs."


def test_meta_line_renders_the_run_mode_in_uppercase(mocker: MockerFixture) -> None:
    """Proves: STORY-064 (charts_tab.md#4.1 meta-line casing fix)

    The shared meta line's ``Mode:`` token renders the run mode in uppercase
    (``Mode: GRADED``), matching the mockup's canonical form.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.GRADED),))
    gateway.set_chart_data(
        1, ChartKind.AVG_TTFT_PER_MODEL, _populated(ChartKind.AVG_TTFT_PER_MODEL)
    )
    controller, view = _make_controller(gateway, FakeEventBus(), mocker)
    # Act
    controller.set_run_context(run_id=1, run_mode=RunMode.GRADED)
    # Assert
    view_model = view.apply.call_args.args[0]
    assert "Mode: GRADED" in view_model.meta_line


# ---------------------------------------------------------------------------
# STORY-064-AC-4: chart-click drill-down routes through the parent controller
# ---------------------------------------------------------------------------


def test_bar_click_routes_drilldown(qtbot: QtBot) -> None:
    """Proves: STORY-064-AC-4

    Clicking a per-model bar element narrows the mounted Details tab to that
    single ``(provider_id, model_name)`` and switches the active tab to
    Details, through the real parent ``ResultController`` wiring (not a stub
    drilldown sink).
    """
    # Arrange
    run = make_run(1, run_mode=RunMode.TASKS)
    result = make_result(
        result_id=1, provider_id="prov-a", provider_name="Ollama Local", model_name="llama3"
    )
    gateway = FakeResultGateway(runs=(run,), results_by_run_id={1: (result,)})
    gateway.set_tasks(1, (make_task(task_id="task-1"),))
    gateway.set_chart_data(
        1,
        ChartKind.AVG_TTFT_PER_MODEL,
        _populated(ChartKind.AVG_TTFT_PER_MODEL, category="Ollama Local / llama3"),
    )
    controller = ResultController(collaborators=_make_result_collaborators(gateway, FakeEventBus()))
    view = ResultView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    view.show()
    qtbot.wait(0)
    tab_widget = cast("QTabWidget", view.findChild(QTabWidget, "result_widget.tabs"))
    tab_widget.setCurrentIndex(2)  # "charts"
    canvas = cast("QWidget", view.findChild(QWidget, "charts_tab.canvas"))
    # Act
    position = QPointF(canvas.width() * 0.5, canvas.height() * 0.5)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(event)
    # Assert -- the Details sub-controller narrowed to the clicked model
    details_state = controller._details_tab.current_view_state
    assert details_state is not None
    assert details_state.filters.models == (("prov-a", "llama3"),)
    # Assert -- the active tab switched to Details
    assert tab_widget.currentIndex() == 1


# ---------------------------------------------------------------------------
# STORY-064-AC-5 / EC-RES-4: export uses the active theme's palette
# ---------------------------------------------------------------------------


def test_export_uses_active_theme_palette(mocker: MockerFixture) -> None:
    """Proves: STORY-064-AC-5

    Exporting the active chart renders from the active theme's palette (here,
    the dark-default fallback since no ``ThemeManager`` is wired), not the OS
    palette -- decoded back from the PNG bytes and compared against the dark
    theme's ``bg.window`` token colour. Covers EC-RES-4.
    """
    # Arrange
    gateway = FakeResultGateway(runs=(make_run(1, run_mode=RunMode.TASKS),))
    gateway.set_chart_data(
        1, ChartKind.AVG_TTFT_PER_MODEL, _populated(ChartKind.AVG_TTFT_PER_MODEL)
    )
    controller, _view = _make_controller(gateway, FakeEventBus(), mocker)
    controller.set_run_context(run_id=1, run_mode=RunMode.TASKS)
    dark_tokens = make_dark_theme_tokens(platform_kind=PlatformKind.UNKNOWN)
    expected = QColor(resolve_color(dark_tokens, "bg.window"))
    # Act
    payload = controller.render_chart_export(fmt="png")
    # Assert
    image = QImage.fromData(payload)
    assert not image.isNull()
    assert (image.width(), image.height()) == (painting.EXPORT_WIDTH, painting.EXPORT_HEIGHT)
    assert image.pixelColor(0, 0) == expected
