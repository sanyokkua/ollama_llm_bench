"""``SummaryTabView`` -- the Summary tab's passive Qt view (STORY-062).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/summary_tab.md`` §2
(layout), §6-§7 (filter bar, column-visibility control and reordering), §10 (the 500 ms
debounce). Passive View: renders a ``SummaryViewModel`` via ``apply()`` and emits
widget-local Qt signals on user interaction; imports no backend symbol beyond
``backend.domain`` DTOs/enums it renders.

Documented scope simplifications (pre-approved; see the story's return summary):

- The per-column filter's domain is the column's fixed, closed status/layer set (not a
  dynamic "distinct values actually present" scan) -- selecting a value that never
  occurred in this run is a harmless no-op filter.
- A per-column filter menu applies each toggle immediately and closes per Qt's stock
  ``QMenu`` behaviour; the user re-opens the menu (right-click again) to change another
  value, rather than a custom multi-check-without-closing menu implementation.
- A column drag-reorder repositions only the currently *visible* headers; any hidden
  column keeps its previous relative order, appended after the newly-ordered visible set.
"""

from collections.abc import Callable
from functools import partial
from typing import Protocol, cast

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.adapters.qt_table_models import SummaryTableRow, make_summary_table_model
from ollama_llm_bench.ui.results._internal.summary_tab import select
from ollama_llm_bench.ui.results._internal.summary_tab.controller import SummaryTabController
from ollama_llm_bench.ui.results._internal.summary_tab.select import (
    ChipDomains,
    SummaryColumnKey,
    SummaryFilters,
    SummaryViewState,
)
from ollama_llm_bench.ui.results._internal.theme_lookup import resolve_spacing_tokens
from ollama_llm_bench.ui.results.models import SummaryViewModel
from ollama_llm_bench.ui.theme import PlatformKind

__all__: list[str] = ["SummaryTabView"]

_DEBOUNCE_MS = 500


class _RowsSettable(Protocol):
    """The ``_FrozenRowTableModel.set_rows`` surface -- ``make_summary_table_model``
    returns the erased ``QAbstractTableModel`` type; this local Protocol recovers
    the ``set_rows`` shape without reaching into ``adapters.qt_table_models._internal``.
    """

    def set_rows(self, *, headers: tuple[str, ...], rows: tuple[SummaryTableRow, ...]) -> None: ...


class _FilterChipButton(QPushButton):
    """A checkable multi-select filter chip: label ``"<Label> N / M"``, default
    all-checked (§6). Not ``ui.shared.MultiCheckFilterButtonWidget``: that widget
    defaults to none-checked and renders a different label format."""

    selection_changed = Signal(object)  # frozenset[str]

    def __init__(self, *, label: str) -> None:
        super().__init__()
        self.setObjectName(f"summary_tab.chip.{label.lower()}")
        self.setAccessibleName(f"Filter by {label}")
        self._label = label
        self._options: tuple[str, ...] = ()
        self._checked: set[str] = set()
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._refresh_role()

    def set_options(
        self,
        options: tuple[str, ...],
        *,
        checked: frozenset[str],
        display_labels: dict[str, str] | None = None,
    ) -> None:
        """Rebuild the menu options and checked state (never emits a signal)."""
        labels = display_labels or {}
        self._options = options
        self._checked = set(checked)
        self._menu.clear()
        for option in options:
            action = QAction(labels.get(option, option), self._menu)
            action.setCheckable(True)
            action.setChecked(option in self._checked)
            action.toggled.connect(partial(self._on_option_toggled, option))
            self._menu.addAction(action)
        self._refresh_label()
        self._refresh_role()

    def _on_option_toggled(self, option: str, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if checked:
            self._checked.add(option)
        else:
            self._checked.discard(option)
        self._refresh_label()
        self._refresh_role()
        self.selection_changed.emit(frozenset(self._checked))

    def _refresh_label(self) -> None:
        self.setText(f"{self._label} {len(self._checked)} / {len(self._options)}")

    def _refresh_role(self) -> None:
        is_active = len(self._checked) < len(self._options)
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
        columns: tuple[SummaryColumnKey, ...],
        visible: frozenset[SummaryColumnKey],
        on_toggle: Callable[[SummaryColumnKey, bool], None],
        on_reset: Callable[[], None],
    ) -> None:
        # A non-null Qt parent gives this top-level Qt.Popup-flagged widget a C++
        # owner, so it survives after `_open_columns_popover` returns and its local
        # Python variable goes out of scope (Qt reparents Popup-flagged widgets to
        # a top-level window regardless of `parent`, but keeps the ownership link).
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("summary_tab.columns_popover")
        layout = QVBoxLayout(self)
        for column in columns:
            checkbox = QCheckBox(select.column_label(column))
            checkbox.setObjectName(f"summary_tab.columns_popover.column.{column.value}")
            checkbox.setChecked(column in visible)
            checkbox.setAccessibleName(select.column_label(column))
            if column is SummaryColumnKey.PROVIDER_MODEL:
                # Pinned first column; never hideable (§7) -- shown checked and
                # disabled rather than omitted, so it still counts toward the
                # Columns button's N / M fraction.
                checkbox.setEnabled(False)
            else:
                checkbox.toggled.connect(partial(on_toggle, column))
            layout.addWidget(checkbox)
        footer = QHBoxLayout()
        reset_button = QPushButton("Reset")
        reset_button.setObjectName("summary_tab.columns_popover.reset_button")
        reset_button.setProperty("role", "outlined-muted-button")
        reset_button.setAccessibleName("Reset columns")
        reset_button.clicked.connect(on_reset)
        footer.addWidget(reset_button)
        footer.addStretch()
        done_button = QPushButton("Done")
        done_button.setObjectName("summary_tab.columns_popover.done_button")
        done_button.setProperty("role", "primary-button")
        done_button.setAccessibleName("Done choosing columns")
        done_button.clicked.connect(self.close)
        footer.addWidget(done_button)
        layout.addLayout(footer)


class SummaryTabView(QWidget):
    """Passive Summary tab body: the filter bar, the aggregate table, the
    column-visibility popover, and the debounced live re-aggregation timer."""

    def __init__(self, *, platform_kind: PlatformKind = PlatformKind.UNKNOWN) -> None:
        super().__init__()
        self.setObjectName("summary_tab.view")
        self._platform_kind = platform_kind
        self._controller: SummaryTabController | None = None
        self._visible_columns: tuple[SummaryColumnKey, ...] = ()
        self._build_ui()

    def _build_ui(self) -> None:
        tokens = resolve_spacing_tokens(platform_kind=self._platform_kind)
        spacing = tokens.spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(spacing.sm)

        self._empty_label = QLabel("")
        self._empty_label.setObjectName("summary_tab.empty_message")
        self._empty_label.setWordWrap(True)
        root.addWidget(self._empty_label)

        self._filter_bar = self._build_filter_bar(spacing_px=spacing.sm)
        root.addWidget(self._filter_bar)

        self._table_view = QTableView()
        self._table_view.setObjectName("summary_tab.table")
        self._table_view.setAccessibleName("Summary results table")
        header = self._table_view.horizontalHeader()
        header.setSectionsMovable(True)
        header.sectionClicked.connect(self._on_section_clicked)
        header.sectionMoved.connect(self._on_section_moved)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu_requested)
        model = make_summary_table_model(headers=(), rows=())
        self._table_view.setModel(model)
        self._table_model = cast("_RowsSettable", model)
        root.addWidget(self._table_view, 1)

        self._recompute_timer = QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.setInterval(_DEBOUNCE_MS)
        self._recompute_timer.timeout.connect(self._on_recompute_timer_fired)

    def _build_filter_bar(self, *, spacing_px: int) -> QWidget:
        bar = QWidget()
        bar.setObjectName("summary_tab.filter_bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing_px)
        self._chip_models = _FilterChipButton(label="Models")
        self._chip_models.setObjectName("summary_tab.chip.models")
        self._chip_verdict = _FilterChipButton(label="Verdict")
        self._chip_verdict.setObjectName("summary_tab.chip.verdict")
        self._chip_difficulty = _FilterChipButton(label="Difficulty")
        self._chip_difficulty.setObjectName("summary_tab.chip.difficulty")
        self._chip_category = _FilterChipButton(label="Category")
        self._chip_category.setObjectName("summary_tab.chip.category")
        for chip_name, chip in (
            ("models", self._chip_models),
            ("verdict", self._chip_verdict),
            ("difficulty", self._chip_difficulty),
            ("category", self._chip_category),
        ):
            chip.selection_changed.connect(partial(self._on_chip_changed, chip_name))
            row.addWidget(chip)
        row.addStretch()
        self._clear_filters_button = QPushButton("Clear filters")
        self._clear_filters_button.setObjectName("summary_tab.clear_filters")
        self._clear_filters_button.setAccessibleName("Clear filters")
        self._clear_filters_button.setProperty("role", "outlined-muted-button")
        self._clear_filters_button.clicked.connect(self._on_clear_filters_clicked)
        row.addWidget(self._clear_filters_button)
        self._columns_button = QPushButton("Columns")
        self._columns_button.setObjectName("summary_tab.columns_button")
        self._columns_button.setAccessibleName("Show or hide columns")
        self._columns_button.setProperty("role", "outlined-muted-button")
        self._columns_button.clicked.connect(self._open_columns_popover)
        row.addWidget(self._columns_button)
        return bar

    def bind_controller(self, controller: SummaryTabController) -> None:
        """Attach the sub-controller every user-interaction signal routes to."""
        self._controller = controller

    def schedule_recompute(self) -> None:
        """(Re)start the 500 ms debounce timer for a live-run re-aggregation (§10)."""
        self._recompute_timer.start()

    def apply(
        self,
        vm: SummaryViewModel,
        *,
        domains: ChipDomains,
        view_state: SummaryViewState,
        visible_columns: tuple[SummaryColumnKey, ...],
    ) -> None:
        """Render the filter bar, aggregate table, and empty-state message from ``vm``."""
        self._visible_columns = visible_columns
        self._filter_bar.setVisible(True)
        self._table_view.setVisible(True)
        self._apply_chips(domains, view_state.filters)
        self._clear_filters_button.setEnabled(_has_active_filters(view_state))
        self._columns_button.setText(
            f"Columns {len(view_state.layout.visible)} / {len(view_state.layout.order)}"
        )
        self._table_model.set_rows(
            headers=vm.columns, rows=tuple(SummaryTableRow(cells=row) for row in vm.rows)
        )
        self._empty_label.setText(vm.empty_state_message or "")
        self._empty_label.setVisible(vm.empty_state_message is not None)

    def apply_no_run(self, message: str) -> None:
        """Render the "select a run" state: no chips, no table, just the message."""
        self._filter_bar.setVisible(False)
        self._table_view.setVisible(False)
        self._empty_label.setText(message)
        self._empty_label.setVisible(True)

    def _apply_chips(self, domains: ChipDomains, filters: SummaryFilters) -> None:
        model_keys = tuple(key for key, _ in domains.models)
        self._chip_models.set_options(
            model_keys,
            display_labels=dict(domains.models),
            checked=frozenset(model_keys) if filters.models is None else filters.models,
        )
        self._chip_verdict.set_options(domains.verdicts, checked=filters.verdicts)
        self._chip_difficulty.set_options(domains.difficulties, checked=filters.difficulties)
        self._chip_category.set_options(
            domains.categories,
            checked=(
                frozenset(domains.categories) if filters.categories is None else filters.categories
            ),
        )

    def _on_chip_changed(self, chip_name: str, selected: frozenset[str]) -> None:
        if self._controller is not None:
            self._controller.on_chip_changed(chip_name, selected)

    def _on_clear_filters_clicked(self) -> None:
        if self._controller is not None:
            self._controller.on_clear_filters_clicked()

    def _on_recompute_timer_fired(self) -> None:
        if self._controller is not None:
            self._controller.recompute_and_push()

    def _open_columns_popover(self) -> None:
        if self._controller is None:
            return
        view_state = self._controller.current_view_state
        if view_state is None:
            return
        popover = _ColumnsPopover(
            parent=self,
            columns=view_state.layout.order,
            visible=view_state.layout.visible,
            on_toggle=self._on_column_toggled,
            on_reset=self._on_columns_reset_clicked,
        )
        anchor = self._columns_button.mapToGlobal(self._columns_button.rect().bottomLeft())
        popover.move(anchor)
        popover.show()

    def _on_column_toggled(self, column: SummaryColumnKey, visible: bool) -> None:  # noqa: FBT001  # Qt signal callback
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
            column for column in view_state.layout.order if column not in new_visible_order
        )
        self._controller.on_columns_reordered(new_visible_order + hidden_columns)

    def _pin_provider_model_column(self, header: QHeaderView) -> None:
        if SummaryColumnKey.PROVIDER_MODEL not in self._visible_columns:
            return
        logical_index = self._visible_columns.index(SummaryColumnKey.PROVIDER_MODEL)
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
        if column is SummaryColumnKey.PROVIDER_MODEL:
            self._chip_models.showMenu()
            return
        self._show_column_filter_menu(column, header.mapToGlobal(position))

    def _show_column_filter_menu(self, column: SummaryColumnKey, global_pos: QPoint) -> None:
        domain = select.column_filter_domain(column)
        view_state = self._controller.current_view_state if self._controller is not None else None
        if domain is None or view_state is None:
            return
        working_selected = set(_selected_values_for(view_state, column, domain))
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
        column: SummaryColumnKey,
        value: str,
        working_selected: set[str],
        checked: bool,  # noqa: FBT001  # Qt signal callback
    ) -> None:
        if checked:
            working_selected.add(value)
        else:
            working_selected.discard(value)
        if self._controller is not None:
            self._controller.on_column_filter_changed(column, frozenset(working_selected))


def _has_active_filters(view_state: SummaryViewState) -> bool:
    filters = view_state.filters
    return bool(
        filters.models is not None
        or filters.categories is not None
        or filters.verdicts != frozenset({"pass", "fail", "ungraded"})
        or filters.difficulties != frozenset({"easy", "medium", "hard"})
        or view_state.column_filters
    )


def _selected_values_for(
    view_state: SummaryViewState, column: SummaryColumnKey, domain: tuple[str, ...]
) -> frozenset[str]:
    for entry in view_state.column_filters:
        if entry.column is column:
            return entry.selected_values
    return frozenset(domain)
