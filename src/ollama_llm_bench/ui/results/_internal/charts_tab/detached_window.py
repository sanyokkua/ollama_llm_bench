"""``DetachedChartWindow`` -- a modeless window forking the parent Charts tab's
filter/option state at open time (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §9
(detach to window). Follows ``_internal/detached.py``'s (``DetachedTableWindow``,
STORY-062/063) Modeless Dialog contract: its own toolbar/canvas, ``setModal(False)``,
``.show()`` never ``.exec()``, and it survives a workspace switch (EC-WS-1) because
it is a top-level window independent of the Benchmark workspace's widget tree.

**Wiring deviation from the story's illustrative sketch (documented in the story's
Notes section):** the "Detach window" click is wired at the parent ``ResultController``
level (``_mount_charts_tab``), not as a ``ChartsTabController.on_detach_clicked``
method returning this window -- that method would require ``charts_tab/controller.py``
to import this module, which imports ``controller.py`` back (a circular import). The
parent controller already imports both and is the natural owner of window
construction, matching how ``DetailsTabView``'s own detach button (§9 of
``details_tab.md``) is a self-contained reparent action with no controller-level
detach method either.
"""

from collections.abc import Callable

import msgspec
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from ollama_llm_bench.backend.domain import ChartKind, RunId, RunMode
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.results._internal.charts_tab.controller import ChartsTabController
from ollama_llm_bench.ui.results._internal.charts_tab.view import ChartsTabView
from ollama_llm_bench.ui.results._internal.charts_tab.view_state import ChartsViewState
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest
from ollama_llm_bench.ui.results.protocols import ResultGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["DetachedChartWindow", "DetachedChartWindowConfig"]


class DetachedChartWindowConfig(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``DetachedChartWindow``'s collaborators (coding-style.md's
    4-parameter hard maximum) -- mirrors ``ResultCollaborators``'s identical
    dependency-bundle pattern. Never crosses ``ui/results/``'s own boundary."""

    gateway: ResultGateway
    bus: EventBus
    run_id: RunId
    run_mode: RunMode
    initial_state: ChartsViewState
    theme_manager: ThemeManager | None = None
    platform_kind: PlatformKind = PlatformKind.UNKNOWN
    on_drilldown: Callable[[ChartDrilldownRequest], None] | None = None


class _NullViewStateStore:
    """A session-only view-state store: every read/write is a no-op.

    A detached chart window's forked state is session state and is never
    persisted (charts_tab.md#9) -- structurally satisfies the surface
    ``ChartsTabController`` calls on its injected ``PerRunViewStateStore``.
    """

    def get_slice(self, **_kwargs: object) -> None:
        """Never called -- ``_NonPersistingChartsTabController`` overrides
        ``set_run_context`` to seed state from the forked snapshot directly."""

    def set_slice(self, **_kwargs: object) -> None:
        """No-op: a detached window's state changes are never written back."""


class _NonPersistingChartsTabController(ChartsTabController):
    """A ``ChartsTabController`` whose view state is seeded once, from the
    parent's forked snapshot, and never reloaded from or written to a store."""

    def __init__(
        self,
        *,
        gateway: ResultGateway,
        bus: EventBus,
        initial_state: ChartsViewState,
        theme_manager: ThemeManager | None,
        platform_kind: PlatformKind,
    ) -> None:
        super().__init__(
            gateway=gateway,
            bus=bus,
            view_state_store=_NullViewStateStore(),  # type: ignore[arg-type]  # structural no-op store, never persists (charts_tab.md#9)
            theme_manager=theme_manager,
            platform_kind=platform_kind,
        )
        self._initial_state = initial_state

    def set_run_context(self, *, run_id: RunId | None, run_mode: RunMode | None) -> None:
        """Seed the forked snapshot directly -- never reads the (no-op) store."""
        self._run_id = run_id
        self._run_mode = run_mode
        if run_id is None or run_mode is None:
            self._view_state = None
            self._chart_data_cache = {}
            if self._view is not None:
                self._view.apply_no_run("Select a run to view its charts.")
            return
        self._view_state = self._initial_state
        self.recompute_and_push()


class DetachedChartWindow(QDialog):
    """A modeless window replicating the Charts tab body for one forked chart
    kind/filter/option snapshot, independent of the parent tab thereafter."""

    def __init__(self, *, config: DetachedChartWindowConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("charts_tab.detached_window")
        self.setWindowTitle(f"Chart — {config.initial_state.last_chart_kind.value}")
        self.setModal(False)
        self._controller = _NonPersistingChartsTabController(
            gateway=config.gateway,
            bus=config.bus,
            initial_state=config.initial_state,
            theme_manager=config.theme_manager,
            platform_kind=config.platform_kind,
        )
        self._view = ChartsTabView(
            platform_kind=config.platform_kind, theme_manager=config.theme_manager
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self._wire_view()
        self._controller.bind(self._view, on_drilldown=config.on_drilldown or (lambda _r: None))
        self._controller.set_run_context(run_id=config.run_id, run_mode=config.run_mode)

    def _wire_view(self) -> None:
        self._view.prev_clicked.connect(self._controller.on_prev_clicked)
        self._view.next_clicked.connect(self._controller.on_next_clicked)
        self._view.chart_kind_selected.connect(
            lambda value: self._controller.on_chart_kind_selected(ChartKind(value))
        )
        self._view.filter_changed.connect(
            lambda chip, values: self._controller.on_filter_changed(chip, tuple(values))
        )
        self._view.option_changed.connect(self._controller.on_option_changed)
        self._view.legend_series_toggled.connect(self._controller.on_legend_series_toggled)
        self._view.clear_filters_clicked.connect(self._controller.on_clear_filters_clicked)
        self._view.chart_element_clicked.connect(self._controller.on_chart_element_clicked)

    @property
    def controller(self) -> ChartsTabController:
        """The window's own, independently-forked ``ChartsTabController`` (test seam)."""
        return self._controller
