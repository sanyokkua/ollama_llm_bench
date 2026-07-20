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
from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.results.protocols import ExportFilenameHelper, ResultGateway
from ollama_llm_bench.ui.theme import PlatformKind

__all__: list[str] = ["FooterViewModel", "ResultCollaborators", "ResultViewModel"]


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
