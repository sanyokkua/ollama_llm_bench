"""``FooterController`` -- the uniform export footer shared by every tab
(STORY-061-AC-3, AC-4, AC-5).

Source of truth: ``docs/v3_specification/05_Result_Widget/description.md`` §5 (footer
uniform contract), §7 (view-only-during-run rule), §10 (empty states -- the "nothing to
export" disable, EC-RES-1). Depends only on ``ResultGateway`` plus the retained UI
helpers (``NativePickers``, ``FileSystemActions``, ``NotificationService``,
``ExportFilenameHelper``) and the Event Bus (D-R-06).
"""

from collections.abc import Callable
import contextlib

import structlog

from ollama_llm_bench.adapters.native_pickers import SavePickerOptions
from ollama_llm_bench.backend.domain import ResultStatus, RunId
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_SETTINGS_CHANGED,
    AppSettingsChangedEvent,
)
from ollama_llm_bench.ui.results.models import FooterViewModel, ResultCollaborators

__all__: list[str] = ["FooterController"]

logger = structlog.get_logger(__name__)

_SETTING_EXPORT_SAVE_DIRECTLY = "ui.export_save_directly"
_LIVE_TOOLTIP = "Disabled — a benchmark is in progress."
_EMPTY_RUN_TOOLTIP = "No completed results to export yet"

_EXPORT_BUTTONS_BY_TAB: dict[str, tuple[str, ...]] = {
    "summary": ("Export CSV", "Export Markdown"),
    "details": ("Export CSV", "Export Markdown"),
    "charts": ("Export PNG", "Export SVG"),
    "run_analysis": ("Export Markdown",),
}
_TABLE_TABS = frozenset({"summary", "details"})
_BUTTON_EXT: dict[str, str] = {
    "Export CSV": "csv",
    "Export Markdown": "md",
    "Export PNG": "png",
    "Export SVG": "svg",
}
_TABLE_KIND_BY_TAB: dict[str, str] = {"summary": "Summary", "details": "Details"}


class FooterController:
    """Owns the export-button cluster, the shared save-destination toggle, and the
    Open-Exports-Folder visibility -- identical in layout on every tab."""

    def __init__(self, *, collaborators: ResultCollaborators) -> None:
        self._collaborators = collaborators
        self._run_id: RunId | None = None
        self._active_tab = "summary"
        self._live = False
        self._on_view_model_changed: Callable[[FooterViewModel], None] | None = None
        logger.debug("footer_controller_constructed")

    def bind(
        self, view: object, *, on_view_model_changed: Callable[[FooterViewModel], None]
    ) -> None:
        """Subscribe to ``_app_settings_changed``, owner-bound to ``view``.

        Args:
            view: The owning widget; bounds the subscription's lifetime.
            on_view_model_changed: Called with the freshly recomputed
                ``FooterViewModel`` whenever the shared setting changes elsewhere.
        """
        self._on_view_model_changed = on_view_model_changed
        self._collaborators.bus.subscribe(
            SIGNAL_APP_SETTINGS_CHANGED, self._on_app_settings_changed, owner=view
        )

    def set_context(self, *, run_id: RunId | None, active_tab: str, live: bool) -> FooterViewModel:
        """Recompute the footer's render state for the current selection/tab/live flag."""
        self._run_id = run_id
        self._active_tab = active_tab
        self._live = live
        return self._build_view_model()

    def on_save_directly_toggled(self, *, checked: bool) -> None:
        """The user flipped the save-destination toggle; persists and broadcasts."""
        logger.debug("footer_save_directly_toggled", checked=checked)
        self._collaborators.gateway.set_setting(
            _SETTING_EXPORT_SAVE_DIRECTLY, "true" if checked else "false"
        )
        self._collaborators.bus.emit(
            SIGNAL_APP_SETTINGS_CHANGED,
            AppSettingsChangedEvent(changed_keys=(_SETTING_EXPORT_SAVE_DIRECTLY,)),
        )

    def on_open_exports_folder_clicked(self) -> None:
        """The Open-Exports-Folder button click; reveals the exports folder."""
        logger.debug("footer_open_exports_folder_clicked")
        with contextlib.suppress(OsAdapterError):
            folder = self._collaborators.file_system_actions.exports_folder_path()
            self._collaborators.file_system_actions.open_in_file_manager(folder)

    def on_export_clicked(self, button_label: str) -> None:
        """An export-button click; composes the filename, writes, and notifies.

        Charts-tab image export is not yet derivable from ``ResultGateway`` alone
        (no ``ChartsTabController`` exists in this shell -- STORY-064 owns the
        chart-canvas render); the click is a documented no-op for that tab in
        this story.
        """
        if self._run_id is None or self._live:
            return
        if not self._has_completed_results(self._run_id):
            return
        kind, content = self._resolve_export_payload(button_label)
        if content is None:
            return
        run = self._collaborators.gateway.get_run(self._run_id)
        ext = _BUTTON_EXT[button_label]
        filename = self._collaborators.export_filenames.compose_filename(
            run=run, kind=kind, ext=ext
        )
        if self._is_save_directly():
            self._write_direct(filename=filename, content=content)
        else:
            self._write_via_picker(filename=filename, content=content)

    def _resolve_export_payload(self, button_label: str) -> tuple[str, str | None]:
        run_id = self._run_id
        if run_id is None:
            return "", None
        if self._active_tab in _TABLE_TABS:
            fmt = _BUTTON_EXT[button_label]
            content = self._collaborators.gateway.serialize_table(run_id, self._active_tab, fmt)
            return _TABLE_KIND_BY_TAB[self._active_tab], content
        if self._active_tab == "run_analysis":
            run = self._collaborators.gateway.get_run(run_id)
            return "RunAnalysis", run.run_analysis or ""
        return "Chart", None

    def _write_direct(self, *, filename: str, content: str) -> None:
        try:
            path = self._collaborators.file_system_actions.write_export_file(
                filename=filename, content=content
            )
        except OsAdapterError as exc:
            logger.warning("footer_export_write_failed", filename=filename, error=str(exc))
            self._collaborators.notifications.show_error(
                "The export could not be saved.", blocking=True
            )
            return
        logger.debug("footer_export_saved", path=path)
        self._collaborators.notifications.show_info(f"Saved to {path}")

    def _write_via_picker(self, *, filename: str, content: str) -> None:
        chosen = self._collaborators.native_pickers.save_file(
            SavePickerOptions(title="Export", suggested_name=filename)
        )
        if chosen is None:
            return
        try:
            self._collaborators.file_system_actions.write_text_file(path=chosen, content=content)
        except OsAdapterError as exc:
            logger.warning("footer_export_write_failed", path=chosen, error=str(exc))
            self._collaborators.notifications.show_error(
                "The export could not be saved.", blocking=True
            )
            return
        logger.debug("footer_export_saved", path=chosen)
        self._collaborators.notifications.show_info(f"Saved to {chosen}")

    def _on_app_settings_changed(self, _payload: object) -> None:
        logger.debug("footer_event_received", signal_name="app_settings_changed")
        vm = self._build_view_model()
        if self._on_view_model_changed is not None:
            self._on_view_model_changed(vm)

    def _build_view_model(self) -> FooterViewModel:
        save_directly = self._is_save_directly()
        exports_enabled, tooltip = self._exports_enabled_and_tooltip()
        return FooterViewModel(
            export_buttons=_EXPORT_BUTTONS_BY_TAB[self._active_tab],
            exports_enabled=exports_enabled,
            disabled_tooltip=tooltip,
            save_directly=save_directly,
            show_open_folder=save_directly,
        )

    def _exports_enabled_and_tooltip(self) -> tuple[bool, str | None]:
        if self._live:
            return False, _LIVE_TOOLTIP
        if self._run_id is None or not self._has_completed_results(self._run_id):
            return False, _EMPTY_RUN_TOOLTIP
        return True, None

    def _has_completed_results(self, run_id: RunId) -> bool:
        return any(
            result.status is ResultStatus.COMPLETED
            for result in self._collaborators.gateway.list_results(run_id)
        )

    def _is_save_directly(self) -> bool:
        return self._collaborators.gateway.get_setting(_SETTING_EXPORT_SAVE_DIRECTLY) == "true"
