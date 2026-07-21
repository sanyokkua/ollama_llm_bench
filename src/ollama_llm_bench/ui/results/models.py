"""Dependency bundle and view-model structs for ``ui/results/`` (STORY-061).

Source of truth: ``docs/v3_specification/05_Result_Widget/implementation_structure.md``
§6 (view-model structs). Only the parent-shell view-models are declared here --
``SummaryViewModel``, ``DetailsViewModel``, ``ChartsViewModel``, and
``JudgeAnalysisViewModel`` are each owned by their own tab story (STORY-062..065).
"""

import msgspec

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.backend.domain import ChartData, ChartKind, HeatmapData, ResultId, RunId
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.results.protocols import ExportFilenameHelper, ResultGateway
from ollama_llm_bench.ui.theme import PlatformKind

__all__: list[str] = [
    "AttemptRow",
    "ChartDrilldownRequest",
    "ChartOptionControl",
    "ChartsViewModel",
    "DetailRowViewModel",
    "DetailsViewModel",
    "FilterChipDomains",
    "FilterChipSelection",
    "FooterViewModel",
    "PhaseEvaluationRow",
    "ResultCollaborators",
    "ResultDetailViewModel",
    "ResultViewModel",
    "SummaryViewModel",
]


class ResultCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_result_widget`` (coding-style.md's
    4-parameter hard maximum)."""

    bus: EventBus
    gateway: ResultGateway
    native_pickers: NativePickers
    clipboard: Clipboard
    file_system_actions: FileSystemActions
    notifications: NotificationService
    export_filenames: ExportFilenameHelper
    platform_kind: PlatformKind = PlatformKind.UNKNOWN


class FooterViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The uniform export-footer render state, shared by every tab (§5)."""

    export_buttons: tuple[str, ...]
    exports_enabled: bool
    disabled_tooltip: str | None
    save_directly: bool
    show_open_folder: bool


class ResultViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The top-level Result widget render state -- header, tab strip, footer (§6)."""

    widget_state: str  # "loading" | "no_run" | "run_selected"
    run_options: tuple[tuple[RunId, str], ...]  # (run_id, effective name), newest first
    selected_run_id: RunId | None
    active_tab: str  # "summary" | "details" | "charts" | "run_analysis"
    footer: FooterViewModel


class SummaryViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Summary tab's render state (STORY-062; implementation_structure.md §6)."""

    columns: tuple[str, ...]  # mode-offered, visible, in order; header text incl. sort caret
    rows: tuple[tuple[str, ...], ...]  # one tuple per surviving (provider, model) group
    empty_state_message: str | None


class DetailRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Details-table row: its result identity plus one formatted cell per visible column."""

    result_id: ResultId
    cells: tuple[str, ...]


class PhaseEvaluationRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the Task Detail Panel's per-phase evaluation section (details_tab.md#9)."""

    phase_name: str
    outcome: str
    measurement: str
    description: str


class AttemptRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the Task Detail Panel's attempt-history section (details_tab.md#9)."""

    attempt_index: int
    timeout_ms: int
    duration_ms: int | None
    outcome: str
    error_kind: str | None
    error_message: str | None


class ResultDetailViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Task Detail Panel payload for one selected result (details_tab.md#9)."""

    result_id: ResultId
    identity_fields: tuple[tuple[str, str], ...]
    system_prompt: str | None
    user_prompt: str | None
    golden_answer: str | None
    model_response: str | None
    has_thinking_block: bool
    raw_response: str | None
    phase_evaluations: tuple[PhaseEvaluationRow, ...]
    judge_reasoning: str
    error_message: str
    attempts: tuple[AttemptRow, ...]


class DetailsViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Pushed by DetailsTabController to DetailsTabView (implementation_structure.md#52)."""

    columns: tuple[str, ...]
    rows: tuple[DetailRowViewModel, ...]
    selected_result_id: ResultId | None
    detail_panel: ResultDetailViewModel | None
    empty_state_message: str | None


class ChartDrilldownRequest(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """An in-process chart-click drill-down request (details_tab.md#10, charts_tab.md#8).

    Exactly one of the four shapes below is populated by a caller:
      - single-model: provider_id + model_name only
      - model-and-status/verdict: provider_id + model_name + (status or verdict)
      - single-result: provider_id + model_name + task_id
      - model-and-category (charts_tab.md#8, chart 10): provider_id + model_name + category
    """

    provider_id: str | None = None
    model_name: str | None = None
    task_id: str | None = None
    status: str | None = None
    verdict: str | None = None
    category: str | None = None


class FilterChipDomains(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Charts tab's five global filter chips' distinct-value domains (charts_tab.md#5).

    ``models`` carries ``(provider_id, model_name, provider_name)`` triples -- the
    snapshot ``provider_name`` is the chip's display label (DD-33), matching
    ``DetailsChipDomains.models``'s identical shape for the sibling tab.
    """

    models: tuple[tuple[str, str, str], ...]
    statuses: tuple[str, ...]
    verdicts: tuple[str, ...]
    categories: tuple[str, ...]
    difficulties: tuple[str, ...]


class FilterChipSelection(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Charts tab's five global filter chips' current selection (charts_tab.md#5).

    An empty tuple means "all selected" (the default), matching
    ``DetailsFilters``'s identical convention.
    """

    models: tuple[tuple[str, str], ...] = ()
    statuses: tuple[str, ...] = ()
    verdicts: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    difficulties: tuple[str, ...] = ()


class ChartOptionControl(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One per-chart option control's render state (charts_tab.md#6).

    ``kind`` is one of ``"toggle"`` (a boolean switch), ``"select"`` (a single choice
    among ``choices``); ``value`` is the control's current stringified value.
    """

    key: str
    label: str
    kind: str
    value: str
    choices: tuple[str, ...] = ()


class ChartsViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Pushed by ChartsTabController to ChartsTabView (implementation_structure.md#53).

    ``dropdown_entries`` carries one ``(chart_kind, label, has_data)`` triple per
    mode-offered chart, in mode-offered order, for the chart-kind dropdown's
    muted ``"(no data)"`` suffix (charts_tab.md#4/#7). Exactly one of
    ``chart_data``/``heatmap_data`` is non-``None`` for a populated non-heatmap/
    heatmap chart respectively; both are ``None`` while ``empty_state_message`` is set.
    """

    chart_kind: ChartKind
    chart_index: int
    chart_count: int
    prev_enabled: bool
    next_enabled: bool
    dropdown_entries: tuple[tuple[ChartKind, str, bool], ...]
    chart_data: ChartData | None
    heatmap_data: HeatmapData | None
    empty_state_message: str | None
    meta_line: str
    filter_domains: FilterChipDomains
    filter_selection: FilterChipSelection
    verdict_filter_visible: bool
    option_controls: tuple[ChartOptionControl, ...]
    hidden_series: tuple[str, ...]
    clear_filters_enabled: bool
    detach_enabled: bool
    export_enabled: bool
