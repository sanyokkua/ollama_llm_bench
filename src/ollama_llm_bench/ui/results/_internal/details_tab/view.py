"""``DetailsTabView`` -- the Details tab's passive Qt view (STORY-063 task 9).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/details_tab.md`` §2
(layout), §3 (column reference), §5 (the seven filter-bar chips), §6 (per-column
filter), §7 (columns popover, the pinned ``Provider / Model`` column), §8 (sorting),
§9 (the Task Detail Panel -- Task 10's scope), §11 (badge rendering), and the 250 ms
live-update debounce (§13). Passive View: renders a ``DetailsViewModel`` via
``apply()`` and emits controller calls on user interaction; imports no backend symbol
beyond ``backend.domain`` DTOs/enums it renders as chip options and badge text.

Structural template: ``ui/results/_internal/summary_tab/view.py`` (``_build_ui``, the
filter-chip button, the columns popover, header ``sectionClicked``/``sectionMoved``/
``customContextMenuRequested`` wiring, the debounce timer). This module retargets that
shape at the Details table model and adds badge rendering; the Task Detail Panel host
itself is Task 10's scope -- ``apply()`` here only forwards ``vm.detail_panel`` to a
placeholder hook Task 10 fills in.

Documented scope simplifications (mirrors the Summary tab's own pre-approved
simplifications; see that module's docstring):

- The per-column filter's domain (§6: "scoped to that column's distinct values in the
  current run") is read from the view's own currently-rendered table rows, not
  recomputed from the backend's unfiltered result set -- the View holds no gateway and
  cannot re-query the run. In practice this differs from a literal whole-run domain
  only while another filter is already narrowing the same column's visible values,
  which is the same trade-off Summary's per-column filter already accepts.
- Right-clicking the pinned ``Provider / Model`` column opens the Models chip's menu
  instead of a redundant separate per-column filter, mirroring Summary's identical
  precedent for its own pinned column.
"""

from collections.abc import Callable
from functools import partial
from typing import Protocol, cast, override

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.adapters.qt_table_models import DetailsTableRow, make_details_table_model
from ollama_llm_bench.backend.domain import Difficulty, ResolutionLayer, ResultStatus, Verdict
from ollama_llm_bench.ui.results._internal.details_tab import select
from ollama_llm_bench.ui.results._internal.details_tab.controller import DetailsTabController
from ollama_llm_bench.ui.results._internal.details_tab.select import (
    DetailsChipDomains,
    DetailsColumnKey,
    DetailsFilters,
    DetailsViewState,
)
from ollama_llm_bench.ui.results._internal.theme_lookup import (
    resolve_spacing_tokens,
    resolve_theme_tokens,
)
from ollama_llm_bench.ui.results.models import DetailsViewModel, ResultDetailViewModel
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["DetailsTabView"]

_DEBOUNCE_MS = 250
_EM_DASH = "—"
_CELL_MARGIN = 4
_CORNER_RADIUS = 4.0

_BADGE_COLUMNS: frozenset[str] = frozenset(
    {
        select.column_label(DetailsColumnKey.STATUS),
        select.column_label(DetailsColumnKey.VERDICT),
        select.column_label(DetailsColumnKey.KEYWORD),
        select.column_label(DetailsColumnKey.COSINE_VERDICT),
        select.column_label(DetailsColumnKey.JUDGE),
        select.column_label(DetailsColumnKey.LAYER),
    }
)

# Maps every string a badge column can ever render (details_tab.md §3/§11) to its
# semantic colour role. The four verdict-family columns (Status excepted) render
# through the shared PASS/FAIL/em-dash formatter; Status and Layer render their own
# lower-case enum values verbatim (select.py's `_CELL_FORMATTERS`).
_TEXT_TO_ROLE: dict[str, str] = {
    "PASS": "success",
    "FAIL": "error",
    _EM_DASH: "muted",
    ResultStatus.COMPLETED.value: "success",
    ResultStatus.FAILED_INFERENCE.value: "error",
    ResultStatus.FAILED_PROVIDER.value: "error",
    ResultStatus.FAILED_TIMEOUT.value: "error",
    ResultStatus.FAILED_JUDGE_TIMEOUT.value: "error",
    ResultStatus.ERRORED.value: "error",
    ResultStatus.PENDING.value: "info",
    ResultStatus.RUNNING_INFERENCE.value: "info",
    ResultStatus.AWAITING_KEYWORD_CHECK.value: "info",
    ResultStatus.AWAITING_COSINE_CHECK.value: "info",
    ResultStatus.AWAITING_JUDGE_CHECK.value: "info",
    ResolutionLayer.KEYWORD.value: "info",
    ResolutionLayer.COSINE.value: "info",
    ResolutionLayer.JUDGE.value: "info",
    ResolutionLayer.SKIP.value: "muted",
}


class _RowsSettable(Protocol):
    """The ``_FrozenRowTableModel[DetailsTableRow]`` surface this view drives --
    ``make_details_table_model`` returns the erased ``QAbstractTableModel`` type; this
    local Protocol recovers ``set_rows``/``rows``/``index`` without reaching into
    ``adapters.qt_table_models._internal``.
    """

    @property
    def rows(self) -> tuple[DetailsTableRow, ...]: ...

    def set_rows(self, *, headers: tuple[str, ...], rows: tuple[DetailsTableRow, ...]) -> None: ...

    def index(self, row: int, column: int, /) -> QModelIndex: ...


def _verdict_chip_label(verdict: Verdict | None) -> str:
    """Return the Verdict chip's option label: PASS/FAIL, or an em-dash for ungraded."""
    if verdict is None:
        return _EM_DASH
    return "PASS" if verdict is Verdict.PASS else "FAIL"


def _layer_chip_label(layer: ResolutionLayer | None) -> str:
    """Return the Layer chip's option label: the layer's value, or an em-dash."""
    return layer.value if layer is not None else _EM_DASH


def _selected_values_for(
    view_state: DetailsViewState, column: DetailsColumnKey
) -> tuple[str, ...] | None:
    """Return the column's currently-active per-column filter, or ``None`` if none."""
    for entry in view_state.filters.column_filters:
        if entry.column == column:
            return entry.allowed_values
    return None


class _FilterChipButton[T](QPushButton):
    """A checkable multi-select filter chip: label ``"<Label> N / M"``, default
    all-checked (§5). Generalised over ``T`` -- unlike Summary's string-only chips,
    six of Details' seven chips filter on typed domain values (`ResultStatus`,
    `Verdict | None`, `ResolutionLayer | None`, `Difficulty`), not bare strings.
    """

    selection_changed = Signal(object)  # tuple[T, ...]

    def __init__(self, *, label: str) -> None:
        super().__init__()
        self.setObjectName(f"details_tab.chip.{label.lower()}")
        self._label = label
        self._items: tuple[tuple[T, str], ...] = ()
        self._checked: set[T] = set()
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._refresh_role()

    def set_options(self, items: tuple[tuple[T, str], ...], *, checked: tuple[T, ...]) -> None:
        """Rebuild the menu options and checked state (never emits a signal).

        Args:
            items: The chip's ``(value, label)`` domain pairs, in display order.
            checked: The filter's current selection; an empty tuple means "all
                selected" (``DetailsFilters``' convention), a non-empty tuple checks
                exactly those values.
        """
        self._items = items
        self._checked = {value for value, _label in items} if not checked else set(checked)
        self._menu.clear()
        for value, label in items:
            action = QAction(label, self._menu)
            action.setCheckable(True)
            action.setChecked(value in self._checked)
            action.toggled.connect(partial(self._on_option_toggled, value))
            self._menu.addAction(action)
        self._refresh_label()
        self._refresh_role()

    def _on_option_toggled(self, value: T, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if checked:
            self._checked.add(value)
        else:
            self._checked.discard(value)
        self._refresh_label()
        self._refresh_role()
        self.selection_changed.emit(tuple(v for v, _label in self._items if v in self._checked))

    def _refresh_label(self) -> None:
        self.setText(f"{self._label} {len(self._checked)} / {len(self._items)}")

    def _refresh_role(self) -> None:
        is_active = len(self._checked) < len(self._items)
        self.setProperty("role", "filter-chip-active" if is_active else "outlined-muted-button")
        self.style().unpolish(self)
        self.style().polish(self)


class _ColumnsPopover(QWidget):
    """The column-visibility popover: one checkbox per mode-offered column plus a
    ``Reset``/``Done`` footer, ``Done`` right-most as the primary action (§7)."""

    def __init__(
        self,
        *,
        parent: QWidget,
        columns: tuple[DetailsColumnKey, ...],
        visible: tuple[DetailsColumnKey, ...],
        on_toggle: Callable[[DetailsColumnKey, bool], None],
        on_reset: Callable[[], None],
    ) -> None:
        # A non-null Qt parent gives this top-level Qt.Popup-flagged widget a C++
        # owner, so it survives after `_open_columns_popover` returns and its local
        # Python variable goes out of scope (Qt reparents Popup-flagged widgets to
        # a top-level window regardless of `parent`, but keeps the ownership link).
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("details_tab.columns_popover")
        layout = QVBoxLayout(self)
        for column in columns:
            checkbox = QCheckBox(select.column_label(column))
            checkbox.setChecked(column in visible)
            if column is DetailsColumnKey.PROVIDER_MODEL:
                # Pinned first column; never hideable (§7) -- shown checked and
                # disabled rather than omitted, so it still counts toward the
                # Columns button's N / M fraction.
                checkbox.setEnabled(False)
            else:
                checkbox.toggled.connect(partial(on_toggle, column))
            layout.addWidget(checkbox)
        footer = QHBoxLayout()
        reset_button = QPushButton("Reset")
        reset_button.setProperty("role", "outlined-muted-button")
        reset_button.clicked.connect(on_reset)
        footer.addWidget(reset_button)
        footer.addStretch()
        done_button = QPushButton("Done")
        done_button.setProperty("role", "primary-button")
        done_button.clicked.connect(self.close)
        footer.addWidget(done_button)
        layout.addLayout(footer)


class _BadgeDelegate(QStyledItemDelegate):
    """Paints a semantic-colour badge for the Status/Verdict/Keyword/Cosine
    verdict/Judge/Layer cells (§11) instead of plain text.

    Badges are custom-painted, not QSS-driven -- the theme stylesheet has no
    ``role="badge-*"`` selector, and neither ``resolve_verdict_color`` nor
    ``VerdictDisplayState`` cover the "info" role this tab's in-progress statuses and
    keyword/cosine/judge layers need. Mirrors ``StatusBadgeDelegate``
    (``ui/resume_benchmark/_internal/status_badge_delegate.py``)'s paint shape.
    """

    def __init__(
        self,
        *,
        headers: tuple[str, ...],
        theme_manager: ThemeManager | None,
        platform_kind: PlatformKind,
    ) -> None:
        super().__init__()
        self._headers = headers
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind

    def set_headers(self, headers: tuple[str, ...]) -> None:
        """Update the visible-column labels this delegate uses to recognise badge cells."""
        self._headers = headers

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole)
        role = self._badge_role(index.column(), text)
        if role is None or self._theme_manager is None or not isinstance(text, str):
            super().paint(painter, option, index)
            return
        self._paint_badge(painter, option, text, role)

    def _badge_role(self, column_index: int, text: object) -> str | None:
        if column_index >= len(self._headers) or self._headers[column_index] not in _BADGE_COLUMNS:
            return None
        if not isinstance(text, str):
            return None
        return _TEXT_TO_ROLE.get(text)

    def _paint_badge(
        self, painter: QPainter, option: QStyleOptionViewItem, text: str, role: str
    ) -> None:
        theme_manager = self._theme_manager
        if theme_manager is None:
            return
        tokens = resolve_theme_tokens(
            theme_manager=theme_manager, platform_kind=self._platform_kind
        )
        fill_hex = resolve_color(tokens, f"{role}.fill")
        base_hex = resolve_color(tokens, f"{role}.base")
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        rect = cell_rect.adjusted(_CELL_MARGIN, _CELL_MARGIN, -_CELL_MARGIN, -_CELL_MARGIN)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(fill_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(rect), _CORNER_RADIUS, _CORNER_RADIUS)
        painter.setPen(QColor(base_hex))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class DetailsTabView(QWidget):
    """Passive Details tab body: the filter bar, the results table with badge
    rendering, the column-visibility popover, and the debounced live-update timer.
    """

    def __init__(
        self,
        *,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
        theme_manager: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("details_tab.view")
        self._platform_kind = platform_kind
        self._theme_manager = theme_manager
        self._controller: DetailsTabController | None = None
        self._visible_columns: tuple[DetailsColumnKey, ...] = ()
        self._export_enabled = False
        self._pending_detail_panel: ResultDetailViewModel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        tokens = resolve_spacing_tokens(platform_kind=self._platform_kind)
        spacing = tokens.spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(spacing.sm)

        self._empty_label = QLabel("")
        self._empty_label.setObjectName("details_tab.empty_message")
        self._empty_label.setWordWrap(True)
        root.addWidget(self._empty_label)

        self._filter_bar = self._build_filter_bar(spacing_px=spacing.sm)
        root.addWidget(self._filter_bar)

        self._table_view = QTableView()
        self._table_view.setObjectName("details_tab.table")
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self._table_view.horizontalHeader()
        header.setSectionsMovable(True)
        header.sectionClicked.connect(self._on_section_clicked)
        header.sectionMoved.connect(self._on_section_moved)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu_requested)
        model = make_details_table_model(headers=(), rows=())
        self._table_view.setModel(model)
        self._table_model = cast("_RowsSettable", model)
        self._badge_delegate = _BadgeDelegate(
            headers=(), theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        self._table_view.setItemDelegate(self._badge_delegate)
        selection_model = self._table_view.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_current_row_changed)
        root.addWidget(self._table_view, 1)

        self._recompute_timer = QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.setInterval(_DEBOUNCE_MS)
        self._recompute_timer.timeout.connect(self._on_recompute_timer_fired)

    def _build_filter_bar(self, *, spacing_px: int) -> QWidget:
        bar = QWidget()
        bar.setObjectName("details_tab.filter_bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing_px)
        self._chip_models: _FilterChipButton[tuple[str, str]] = _FilterChipButton(label="Models")
        self._chip_tasks: _FilterChipButton[str] = _FilterChipButton(label="Tasks")
        self._chip_categories: _FilterChipButton[str] = _FilterChipButton(label="Category")
        self._chip_statuses: _FilterChipButton[ResultStatus] = _FilterChipButton(label="Status")
        self._chip_verdicts: _FilterChipButton[Verdict | None] = _FilterChipButton(label="Verdict")
        self._chip_layers: _FilterChipButton[ResolutionLayer | None] = _FilterChipButton(
            label="Layer"
        )
        self._chip_difficulties: _FilterChipButton[Difficulty] = _FilterChipButton(
            label="Difficulty"
        )
        chips: tuple[tuple[str, QPushButton], ...] = (
            ("models", self._chip_models),
            ("tasks", self._chip_tasks),
            ("categories", self._chip_categories),
            ("statuses", self._chip_statuses),
            ("verdicts", self._chip_verdicts),
            ("layers", self._chip_layers),
            ("difficulties", self._chip_difficulties),
        )
        for chip_name, chip in chips:
            cast("_FilterChipButton[object]", chip).selection_changed.connect(
                partial(self._on_chip_changed, chip_name)
            )
            row.addWidget(chip)
        row.addStretch()
        self._clear_filters_button = QPushButton("Clear filters")
        self._clear_filters_button.setObjectName("details_tab.clear_filters")
        self._clear_filters_button.setProperty("role", "outlined-muted-button")
        self._clear_filters_button.clicked.connect(self._on_clear_filters_clicked)
        row.addWidget(self._clear_filters_button)
        self._columns_button = QPushButton("Columns")
        self._columns_button.setObjectName("details_tab.columns_button")
        self._columns_button.setProperty("role", "outlined-muted-button")
        self._columns_button.clicked.connect(self._open_columns_popover)
        row.addWidget(self._columns_button)
        return bar

    def bind_controller(self, controller: DetailsTabController) -> None:
        """Attach the sub-controller every user-interaction signal routes to."""
        self._controller = controller

    def schedule_recompute(self) -> None:
        """(Re)start the 250 ms debounce timer for a live-data-changed event (§13)."""
        self._recompute_timer.start()

    def apply(
        self, vm: DetailsViewModel, *, view_state: DetailsViewState, domains: DetailsChipDomains
    ) -> None:
        """Render the filter bar, results table, and empty-state message from ``vm``."""
        self._visible_columns = tuple(
            c for c in view_state.columns.order if c in view_state.columns.visible
        )
        self._filter_bar.setVisible(True)
        self._table_view.setVisible(True)
        self._apply_chips(domains, view_state)
        self._clear_filters_button.setEnabled(not view_state.filters.is_default())
        self._columns_button.setText(
            f"Columns {len(view_state.columns.visible)} / {len(view_state.columns.order)}"
        )
        self._table_model.set_rows(
            headers=vm.columns,
            rows=tuple(DetailsTableRow(result_id=r.result_id, cells=r.cells) for r in vm.rows),
        )
        self._badge_delegate.set_headers(vm.columns)
        self._empty_label.setText(vm.empty_state_message or "")
        self._empty_label.setVisible(vm.empty_state_message is not None)
        self._reselect_row(vm.selected_result_id)
        self._on_detail_panel_updated(vm.detail_panel)

    def apply_no_run(self, message: str) -> None:
        """Render the "select a run" state: no chips, no table, just the message."""
        self._filter_bar.setVisible(False)
        self._table_view.setVisible(False)
        self._empty_label.setText(message)
        self._empty_label.setVisible(True)

    def set_export_enabled(self, *, enabled: bool) -> None:
        """Track the run's terminal-state readiness for this tab's export action.

        This tab's export/bulk-export toolbar (§14) is a later story's scope; there is
        no control to enable/disable yet, so this only retains the state for that
        future wiring.
        """
        self._export_enabled = enabled

    def _apply_chips(self, domains: DetailsChipDomains, view_state: DetailsViewState) -> None:
        filters: DetailsFilters = view_state.filters
        is_graded = DetailsColumnKey.VERDICT in view_state.columns.order
        self._chip_models.set_options(
            tuple(
                ((m.provider_id, m.model_name), f"{m.provider_name} / {m.model_name}")
                for m in domains.models
            ),
            checked=filters.models,
        )
        self._chip_tasks.set_options(
            tuple((task_id, task_id) for task_id in domains.tasks), checked=filters.tasks
        )
        self._chip_categories.set_options(
            tuple((category, category) for category in domains.categories),
            checked=filters.categories,
        )
        self._chip_statuses.set_options(
            tuple((status, status.value) for status in domains.statuses), checked=filters.statuses
        )
        self._chip_verdicts.set_options(
            tuple((verdict, _verdict_chip_label(verdict)) for verdict in domains.verdicts),
            checked=filters.verdicts,
        )
        self._chip_verdicts.setVisible(is_graded)
        self._chip_layers.set_options(
            tuple((layer, _layer_chip_label(layer)) for layer in domains.layers),
            checked=filters.layers,
        )
        self._chip_layers.setVisible(is_graded)
        self._chip_difficulties.set_options(
            tuple((difficulty, difficulty.value) for difficulty in domains.difficulties),
            checked=filters.difficulties,
        )

    def _reselect_row(self, result_id: int | None) -> None:
        selection_model = self._table_view.selectionModel()
        selection_model.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._reselect_row_impl(selection_model, result_id)
        finally:
            selection_model.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _reselect_row_impl(
        self, selection_model: QItemSelectionModel, result_id: int | None
    ) -> None:
        if result_id is not None:
            for row_index, row in enumerate(self._table_model.rows):
                if row.result_id == result_id:
                    index = self._table_model.index(row_index, 0)
                    selection_model.select(
                        index,
                        QItemSelectionModel.SelectionFlag.ClearAndSelect
                        | QItemSelectionModel.SelectionFlag.Rows,
                    )
                    self._table_view.setCurrentIndex(index)
                    return
        selection_model.clearSelection()

    def _on_detail_panel_updated(self, panel: ResultDetailViewModel | None) -> None:
        """Cache the Task Detail Panel payload; Task 10 mounts and renders it here."""
        self._pending_detail_panel = panel

    def _on_chip_changed(self, chip_name: str, selected: tuple[object, ...]) -> None:
        if self._controller is not None:
            self._controller.on_chip_changed(chip_name, selected)

    def _on_clear_filters_clicked(self) -> None:
        if self._controller is not None:
            self._controller.on_clear_filters_clicked()

    def _on_recompute_timer_fired(self) -> None:
        if self._controller is not None:
            self._controller.recompute_and_push()

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if self._controller is None:
            return
        rows = self._table_model.rows
        if not current.isValid() or not (0 <= current.row() < len(rows)):
            self._controller.on_row_selected(None)
            return
        self._controller.on_row_selected(rows[current.row()].result_id)

    def _open_columns_popover(self) -> None:
        if self._controller is None:
            return
        view_state = self._controller.current_view_state
        if view_state is None:
            return
        popover = _ColumnsPopover(
            parent=self,
            columns=view_state.columns.order,
            visible=view_state.columns.visible,
            on_toggle=self._on_column_toggled,
            on_reset=self._on_columns_reset_clicked,
        )
        anchor = self._columns_button.mapToGlobal(self._columns_button.rect().bottomLeft())
        popover.move(anchor)
        popover.show()

    def _on_column_toggled(self, column: DetailsColumnKey, visible: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if self._controller is not None:
            self._controller.on_column_toggled(column, visible=visible)

    def _on_columns_reset_clicked(self) -> None:
        if self._controller is not None:
            self._controller.on_columns_reset_clicked()

    def _on_section_clicked(self, logical_index: int) -> None:
        if self._controller is None or not (0 <= logical_index < len(self._visible_columns)):
            return
        self._controller.on_sort_header_clicked(self._visible_columns[logical_index])

    def _on_section_moved(
        self, _logical_index: int, _old_visual_index: int, _new_visual_index: int
    ) -> None:
        if self._controller is None:
            return
        header = self._table_view.horizontalHeader()
        self._pin_provider_model_column(header)
        view_state = self._controller.current_view_state
        if view_state is None:
            return
        new_visible_order = tuple(
            self._visible_columns[header.logicalIndex(visual)] for visual in range(header.count())
        )
        hidden_columns = tuple(
            column for column in view_state.columns.order if column not in new_visible_order
        )
        self._controller.on_columns_reordered(new_visible_order + hidden_columns)

    def _pin_provider_model_column(self, header: QHeaderView) -> None:
        if DetailsColumnKey.PROVIDER_MODEL not in self._visible_columns:
            return
        logical_index = self._visible_columns.index(DetailsColumnKey.PROVIDER_MODEL)
        if header.visualIndex(logical_index) == 0:
            return
        header.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            header.moveSection(header.visualIndex(logical_index), 0)
        finally:
            header.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _on_header_context_menu_requested(self, position: QPoint) -> None:
        if self._controller is None:
            return
        header = self._table_view.horizontalHeader()
        logical_index = header.logicalIndexAt(position)
        if not (0 <= logical_index < len(self._visible_columns)):
            return
        column = self._visible_columns[logical_index]
        if column is DetailsColumnKey.PROVIDER_MODEL:
            self._chip_models.showMenu()
            return
        self._show_column_filter_menu(column, logical_index, header.mapToGlobal(position))

    def _show_column_filter_menu(
        self, column: DetailsColumnKey, column_index: int, global_pos: QPoint
    ) -> None:
        view_state = self._controller.current_view_state if self._controller is not None else None
        if view_state is None:
            return
        domain = tuple(dict.fromkeys(row.cells[column_index] for row in self._table_model.rows))
        if not domain:
            return
        active_filter = _selected_values_for(view_state, column)
        working_selected = set(domain) if active_filter is None else set(active_filter)
        menu = QMenu(self)
        for value in domain:
            action = QAction(value, menu)
            action.setCheckable(True)
            action.setChecked(value in working_selected)
            action.toggled.connect(
                partial(self._on_column_filter_value_toggled, column, value, working_selected)
            )
            menu.addAction(action)
        menu.exec(global_pos)

    def _on_column_filter_value_toggled(
        self,
        column: DetailsColumnKey,
        value: str,
        working_selected: set[str],
        checked: bool,  # noqa: FBT001  # Qt signal callback
    ) -> None:
        if checked:
            working_selected.add(value)
        else:
            working_selected.discard(value)
        if self._controller is not None:
            self._controller.on_column_filter_changed(column, tuple(working_selected))
