from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, LLMProviderApi

from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    ProvidersConfig,
    RunStartEvent,
    SummaryTableItem,
)


class LogWidgetControllerApi(ABC):
    """
    Controller interface for handling LogWidget events and state updates.
    """

    @abstractmethod
    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to log append events to add text to the log.

        Args:
            callback: Function to invoke with new log lines.
        """

    @abstractmethod
    def subscribe_to_log_clear(self, callback: Callable[[], None]) -> None:
        """
        Subscribe to log clear events to clear the log text.

        Args:
            callback: Function to invoke when log should be cleared.
        """


class ResultWidgetControllerApi(ABC):
    """
    Controller interface for handling ResultWidget events and state updates.
    """

    @abstractmethod
    def handle_run_selection_change(self, run_id: int | None) -> None:
        """
        Handle the run selection dropdown change event by emitting the appropriate event.

        Args:
            run_id: Newly selected run ID, or None if deselected.
        """

    @abstractmethod
    def handle_delete_click(self, _: object) -> None:
        """
        Handle the delete button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_summary_export_csv_click(self, _: object) -> None:
        """
        Handle the summary CSV export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_summary_export_md_click(self, _: object) -> None:
        """
        Handle the summary Markdown export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_detailed_export_csv_click(self, _: object) -> None:
        """
        Handle the detailed CSV export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_detailed_export_md_click(self, _: object) -> None:
        """
        Handle the detailed Markdown export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def subscribe_to_runs_change(self, callback: Callable[[list[tuple[int, str]]], None]) -> None:
        """
        Subscribe to runs list change events to populate the dropdown.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """

    @abstractmethod
    def subscribe_to_run_id_changed(self, callback: Callable[[int | None], None]) -> None:
        """
        Subscribe to run id change events.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_summary_data_change(self, callback: Callable[[list[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to summary data change events to update the summary table.

        Args:
            callback: Function to invoke with new summary table data.
        """

    @abstractmethod
    def subscribe_to_detailed_data_change(self, callback: Callable[[list[SummaryTableItem]], None]) -> None:
        """
        Subscribe to detailed data change events to update the detailed table.

        Args:
            callback: Function to invoke with new detailed table data.
        """

    @abstractmethod
    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to benchmark status change events to update UI state.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """

    @abstractmethod
    def subscribe_to_judge_summary(self, callback: Callable[[JudgeSummaryEvent], None]) -> None:
        """Subscribe to judge summary events emitted after a full-grading run.

        Args:
            callback: Function to invoke with JudgeSummaryEvent (run_id, summary_text).
        """

    @abstractmethod
    def subscribe_to_perf_analysis(self, callback: Callable[[PerfAnalysisEvent], None]) -> None:
        """Subscribe to performance analysis events emitted after Performance or Speed runs.

        Args:
            callback: Function to invoke with PerfAnalysisEvent (run_id, analysis_text).
        """

    @abstractmethod
    def handle_task_selected(self, model_name: str, task_id: str) -> BenchmarkResult | None:
        """Return the full BenchmarkResult for a selected task row, or None if not found.

        Args:
            model_name: Model name from the selected table row.
            task_id: Task ID from the selected table row.
        """

    @abstractmethod
    def export_summary_csv(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export summary as CSV to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """

    @abstractmethod
    def export_summary_md(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export summary as Markdown to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """

    @abstractmethod
    def export_details_csv(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export details as CSV to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """

    @abstractmethod
    def export_details_md(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export details as Markdown to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """

    @abstractmethod
    def get_also_save_to_default(self) -> bool:
        """Return the persisted 'also save to default folder' preference."""

    @abstractmethod
    def set_also_save_to_default(self, value: bool) -> None:
        """Persist the 'also save to default folder' preference.

        Args:
            value: True to also save to the program folder on each export.
        """

    @abstractmethod
    def subscribe_to_chart_data_change(
        self, callback: Callable[[BenchmarkRun | None, list[BenchmarkResult]], None]
    ) -> None:
        """Subscribe to chart data change events to update the charts widget.

        Args:
            callback: Function to invoke with the current BenchmarkRun (or None) and
                list of BenchmarkResult objects for the selected run.
        """

    @abstractmethod
    def get_app_settings_service(self) -> AppSettingsServiceApi:
        """Return the app settings service for persistent KV storage."""


class SettingsWidgetControllerApi(Protocol):
    """Protocol for the settings dialog controller.

    Exposes provider config management and feature flag persistence
    without coupling the UI to concrete service implementations.
    """

    def get_providers_config(self) -> ProvidersConfig | None: ...

    def test_provider_connection(
        self,
        provider_id: str,
        on_result: Callable[[bool, int, str], None],
    ) -> None: ...

    def reload_providers(self) -> None: ...

    def load_providers_yaml(self, path: Path) -> bool: ...

    def save_providers_yaml(self, path: Path, config: ProvidersConfig) -> bool: ...

    def get_setting(self, key: str) -> str | None: ...

    def set_setting(self, key: str, value: str) -> None: ...

    def get_setting_bool(self, key: str, *, default: bool = False) -> bool: ...

    def get_setting_int(self, key: str, *, default: int = 0) -> int: ...

    def test_embedding_connection(
        self,
        provider_id: str,
        model: str,
        on_result: Callable[[bool, int, str], None],
    ) -> None: ...

    def get_models_for_provider(
        self,
        provider_id: str,
        on_result: Callable[[list[str]], None],
    ) -> None: ...

    def reset_settings(self) -> None: ...

    def get_setting_float(self, key: str, *, default: float = 0.0) -> float: ...

    def emit_settings_changed(self, changed_keys: list[str]) -> None: ...

    def save_providers_config_to_standard_path(self, config: ProvidersConfig) -> bool: ...

    def get_provider_instance(self, provider_id: str) -> LLMProviderApi | None: ...


class RunConfigControllerApi(Protocol):
    """Protocol for the unified run configuration controller.

    Provides provider/model discovery, previous run management, and
    benchmark lifecycle control (start, pause, resume, stop).
    """

    def get_provider_names(self) -> list[str]: ...

    def get_models_for_provider(self, provider_name: str) -> list[str]: ...

    def get_unfinished_runs(self) -> list[tuple[int, str]]: ...

    def handle_start_click(self, event: RunStartEvent) -> None: ...

    def handle_pause_click(self) -> None: ...

    def handle_resume_click(self) -> None: ...

    def handle_stop_click(self) -> None: ...

    def handle_resume_run_click(self, run_id: int) -> None: ...

    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None: ...

    def subscribe_to_runs_change(self, callback: Callable[[list[tuple[int, str]]], None]) -> None: ...

    def is_embedding_model(self, model_name: str) -> bool: ...

    def is_embedding_filter_enabled(self) -> bool: ...
