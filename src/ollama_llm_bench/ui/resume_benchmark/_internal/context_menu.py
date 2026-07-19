"""The grouped run-row context menu + per-item gating (STORY-056-AC-4).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``
§3.5 (context menu), §4.2 (action gating). Builds the **Naming, Export, File,
and Destructive** groups only -- the story's Goal defers the **Resume** group
(Resume Run, Retry selected tasks...) to STORY-057, which must *extend* this
same menu-builder function rather than duplicate it.
"""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QWidget

from ollama_llm_bench.ui.resume_benchmark.models import RunRow

__all__: list[str] = ["build_context_menu"]

_EXECUTING_TOOLTIP = "This run is currently running"
_NO_ANALYSIS_TOOLTIP = "No analysis for this run"
_NO_LOG_TOOLTIP = "The run log file is not available"


def build_context_menu(*, row: RunRow, parent: QWidget) -> QMenu:
    """Build the Resume run row's grouped context menu for ``row``.

    Args:
        row: The selected row's pre-derived gating flags.
        parent: The menu's owning widget.

    Returns:
        A ``QMenu`` with one ``QAction`` per item, each carrying an
        ``objectName`` for test/lookup purposes and a disabled-reason
        tooltip on every disabled action.
    """
    menu = QMenu(parent)
    not_executing = not row.is_executing

    _add_action(
        menu,
        object_name="action_clone",
        label="Clone as new retry run",
        enabled=not_executing,
        disabled_tooltip=_EXECUTING_TOOLTIP,
    )
    _add_action(
        menu,
        object_name="action_rename",
        label="Rename…",
        enabled=not_executing,
        disabled_tooltip=_EXECUTING_TOOLTIP,
    )
    menu.addSeparator()
    _add_action(menu, object_name="action_export_summary_csv", label="Export Summary (CSV)")
    _add_action(menu, object_name="action_export_summary_md", label="Export Summary (Markdown)")
    _add_action(menu, object_name="action_export_details_csv", label="Export Details (CSV)")
    _add_action(menu, object_name="action_export_details_md", label="Export Details (Markdown)")
    _add_action(
        menu,
        object_name="action_export_analysis",
        label="Export Run Analysis (Markdown)",
        enabled=row.has_analysis,
        disabled_tooltip=_NO_ANALYSIS_TOOLTIP,
    )
    menu.addSeparator()
    _add_action(
        menu,
        object_name="action_show_log",
        label="Show run-log file",
        enabled=row.log_file_exists,
        disabled_tooltip=_NO_LOG_TOOLTIP,
    )
    menu.addSeparator()
    delete_action = _add_action(
        menu,
        object_name="action_delete",
        label="Delete",
        enabled=not_executing,
        disabled_tooltip=_EXECUTING_TOOLTIP,
    )
    delete_action.setProperty("actionTone", "error")
    return menu


def _add_action(
    menu: QMenu,
    *,
    object_name: str,
    label: str,
    enabled: bool = True,
    disabled_tooltip: str = "",
) -> QAction:
    action = QAction(label, menu)
    action.setObjectName(object_name)
    action.setEnabled(enabled)
    if not enabled:
        action.setToolTip(disabled_tooltip)
    menu.addAction(action)
    return action
