from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, LLMProviderApi

from ollama_llm_bench.backend.core.models import (
    AppReadinessChangedEvent,
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    ProviderConfig,
    ProvidersConfig,
    ReadinessVerdict,
    RunMode,
    RunRenamedEvent,
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
    def subscribe_to_runs_change(
        self, callback: Callable[[list[tuple[int, str]]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to runs list change events to populate the dropdown.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """

    @abstractmethod
    def subscribe_to_run_id_changed(
        self, callback: Callable[[int | None], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to run id change events.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_summary_data_change(
        self, callback: Callable[[list[AvgSummaryTableItem]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to summary data change events to update the summary table.

        Args:
            callback: Function to invoke with new summary table data.
        """

    @abstractmethod
    def subscribe_to_detailed_data_change(
        self, callback: Callable[[list[SummaryTableItem]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to detailed data change events to update the detailed table.

        Args:
            callback: Function to invoke with new detailed table data.
        """

    @abstractmethod
    def subscribe_to_benchmark_status_change(
        self, callback: Callable[[bool], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark status change events to update UI state.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """

    @abstractmethod
    def subscribe_to_judge_summary(
        self, callback: Callable[[JudgeSummaryEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to judge summary events emitted after a full-grading run.

        Args:
            callback: Function to invoke with JudgeSummaryEvent (run_id, summary_text).
        """

    @abstractmethod
    def subscribe_to_perf_analysis(
        self, callback: Callable[[PerfAnalysisEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to performance analysis events emitted after Performance or Speed runs.

        Args:
            callback: Function to invoke with PerfAnalysisEvent (run_id, analysis_text).
        """

    @abstractmethod
    def handle_task_selected(self, model_name: str, task_id: str, prompt_version: str = "v1") -> BenchmarkResult | None:
        """Return the full BenchmarkResult for a selected task row, or None if not found.

        Args:
            model_name: Model name from the selected table row.
            task_id: Task ID from the selected table row.
            prompt_version: Prompt variant version string.
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
        self,
        callback: Callable[[BenchmarkRun | None, list[BenchmarkResult]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to chart data change events to update the charts widget.

        Args:
            callback: Function to invoke with the current BenchmarkRun (or None) and
                list of BenchmarkResult objects for the selected run.
        """

    @abstractmethod
    def get_app_settings_service(self) -> AppSettingsServiceApi:
        """Return the app settings service for persistent KV storage."""

    @abstractmethod
    def get_run_names(self, *, exclude_run_id: int | None = None) -> frozenset[str]:
        """Return the case-folded set of existing run names, optionally excluding one run.

        Args:
            exclude_run_id: Optional run ID whose name should be excluded from the result.

        Returns:
            Frozenset of case-folded run name strings.
        """

    @abstractmethod
    def rename_run(self, *, run_id: int, new_name: str) -> None:
        """Rename a benchmark run and broadcast the change via the event bus.

        Args:
            run_id: Unique ID of the run to rename.
            new_name: The new display name to assign.
        """

    @abstractmethod
    def subscribe_to_run_renamed(
        self, callback: Callable[[RunRenamedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to run renamed events.

        Args:
            callback: Function to invoke with the RunRenamedEvent when a run is renamed.
        """

    @abstractmethod
    def get_run(self, run_id: int) -> BenchmarkRun | None:
        """Return the BenchmarkRun for the given ID, or None if not found.

        Args:
            run_id: Unique identifier of the benchmark run.
        """


class SettingsWidgetControllerApi(Protocol):
    """Protocol for the settings dialog controller.

    Exposes provider config management and feature flag persistence
    without coupling the UI to concrete service implementations.
    """

    def get_providers_config(self) -> ProvidersConfig | None:
        """
        Retrieve the currently loaded providers configuration.

        Returns:
            ProvidersConfig if loaded, or None if not initialized.
        """
        ...

    def test_provider_connection(
        self,
        provider_id: str,
        on_result: Callable[[bool, int, str], None],
    ) -> None:
        """
        Test connectivity to a provider asynchronously.

        Args:
            provider_id: ID of the provider to test.
            on_result: Callback invoked with (success: bool, status_code: int, message: str).
        """
        ...

    def reload_providers(self) -> None:
        """
        Reload the providers configuration from disk and refresh all provider instances.
        """
        ...

    def load_providers_yaml(self, path: Path) -> bool:
        """
        Load a providers.yaml file from a user-specified path.

        Args:
            path: Path to the providers.yaml file.

        Returns:
            True if load succeeded, False otherwise.
        """
        ...

    def save_providers_yaml(self, path: Path, config: ProvidersConfig) -> bool:
        """
        Save a providers configuration to a user-specified path.

        Args:
            path: Path to save the providers.yaml file.
            config: Configuration to persist.

        Returns:
            True if save succeeded, False otherwise.
        """
        ...

    def get_setting(self, key: str) -> str | None:
        """
        Retrieve a string application setting.

        Args:
            key: Setting key.

        Returns:
            Setting value or None if not set.
        """
        ...

    def set_setting(self, key: str, value: str) -> None:
        """
        Persist a string application setting.

        Args:
            key: Setting key.
            value: Value to persist.
        """
        ...

    def get_setting_bool(self, key: str, *, default: bool = False) -> bool:
        """
        Retrieve a boolean application setting.

        Args:
            key: Setting key.
            default: Value to return if setting is not found.

        Returns:
            Setting value parsed as boolean, or default.
        """
        ...

    def get_setting_int(self, key: str, *, default: int = 0) -> int:
        """
        Retrieve an integer application setting.

        Args:
            key: Setting key.
            default: Value to return if setting is not found.

        Returns:
            Setting value parsed as integer, or default.
        """
        ...

    def test_embedding_connection(
        self,
        provider_id: str,
        model: str,
        on_result: Callable[[bool, int, str], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Test connectivity to an embedding provider asynchronously.

        Args:
            provider_id: ID of the embedding provider to test.
            model: Model name to test with.
            on_result: Callback invoked with (success: bool, status_code: int, message: str).
            parent: Optional QObject parent to own the internal signal object, preventing
                premature garbage collection when the calling widget is still alive.
        """
        ...

    def get_models_for_provider(
        self,
        provider_id: str,
        on_result: Callable[[list[str]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Fetch available models for a provider asynchronously.

        Args:
            provider_id: ID of the provider to query.
            on_result: Callback invoked with list of model names.
            parent: Optional QObject parent to own the internal signal object, preventing
                premature garbage collection when the calling widget is still alive.
        """
        ...

    def reset_settings(self) -> None:
        """
        Reset all application settings to their built-in defaults.
        """
        ...

    def reset_providers_to_defaults(self) -> None:
        """Reset all providers and embedding config to factory defaults (bundled providers.yaml).

        Loads the bundled providers.yaml, replaces all DB rows with the bundled content,
        reloads the registry, and refreshes the UI.
        """
        ...

    def get_bundled_providers_config(self) -> ProvidersConfig | None:
        """Load and return the bundled default providers.yaml config without modifying storage.

        Returns:
            ProvidersConfig from the bundled YAML, or None if loading fails.
        """
        ...

    def get_setting_float(self, key: str, *, default: float = 0.0) -> float:
        """
        Retrieve a float application setting.

        Args:
            key: Setting key.
            default: Value to return if setting is not found.

        Returns:
            Setting value parsed as float, or default.
        """
        ...

    def emit_settings_changed(self, changed_keys: list[str]) -> None:
        """
        Broadcast that specific settings have been changed.

        Args:
            changed_keys: List of setting keys that were modified.
        """
        ...

    def save_providers_config_to_standard_path(self, config: ProvidersConfig) -> bool:
        """
        Save a providers configuration to the application's standard location.

        Args:
            config: Configuration to persist.

        Returns:
            True if save succeeded, False otherwise.
        """
        ...

    def get_provider_instance(self, provider_id: str) -> LLMProviderApi | None:
        """
        Retrieve a provider instance by its ID.

        Args:
            provider_id: ID of the provider to retrieve.

        Returns:
            LLMProviderApi instance or None if not found.
        """
        ...

    def is_embedding_model(self, model_name: str) -> bool:
        """Return True if model_name matches a known embedding-model pattern.

        Args:
            model_name: The model name string to classify.

        Returns:
            True if the name matches a known embedding pattern.
        """
        ...

    def get_default_provider_config(self, provider_id: str) -> ProviderConfig | None:
        """Return the YAML default config for provider_id, or None if not found.

        Args:
            provider_id: ID of the provider to look up in YAML defaults.

        Returns:
            ProviderConfig from YAML defaults, or None if file is absent or provider not found.
        """
        ...

    def set_last_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result for a provider.

        Args:
            provider_id: Provider to update.
            status: Health status string (e.g. "healthy" or "down").
            tested_at: ISO-8601 UTC timestamp of the test.
            message: Human-readable result message.
        """
        ...

    def subscribe_to_provider_registry_reloaded(
        self, callback: Callable[[], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe callback to provider-registry reload events.

        Args:
            callback: Function to invoke when the registry is reloaded.
        """
        ...

    def subscribe_to_app_readiness_changed(
        self, callback: Callable[[AppReadinessChangedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to app readiness changed events.

        Args:
            callback: Function to invoke with the new readiness snapshot.
        """
        ...


class RunConfigControllerApi(Protocol):
    """Protocol for the unified run configuration controller.

    Provides provider/model discovery, previous run management, and
    benchmark lifecycle control (start, pause, resume, stop).
    """

    def get_provider_names(self) -> list[str]:
        """
        Retrieve the list of available LLM provider names.

        Returns:
            List of provider names (e.g., ["openai", "anthropic", "ollama"]).
        """
        ...

    def get_models_for_provider(self, provider_name: str) -> list[str]:
        """
        Retrieve available models for a specific provider.

        Args:
            provider_name: Name of the provider.

        Returns:
            List of model names available from this provider.
        """
        ...

    def get_unfinished_runs(self) -> list[tuple[int, str]]:
        """
        Retrieve benchmark runs that have not yet completed.

        Returns:
            List of (run_id, run_name) tuples for unfinished runs.
        """
        ...

    def handle_start_click(self, event: RunStartEvent) -> None:
        """
        Handle the start benchmark button click event.

        Args:
            event: RunStartEvent containing configuration for the new run.
        """
        ...

    def handle_pause_click(self) -> None:
        """
        Handle the pause benchmark button click event.
        """
        ...

    def handle_resume_click(self) -> None:
        """
        Handle the resume benchmark button click event.
        """
        ...

    def handle_stop_click(self) -> None:
        """
        Handle the stop benchmark button click event.
        """
        ...

    def handle_resume_run_click(self, run_id: int) -> None:
        """
        Handle the resume previous run button click event.

        Args:
            run_id: ID of the run to resume.
        """
        ...

    def subscribe_to_benchmark_status_change(
        self, callback: Callable[[bool], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark execution status changes.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """
        ...

    def subscribe_to_runs_change(
        self, callback: Callable[[list[tuple[int, str]]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to changes in the list of available runs.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """
        ...

    def is_embedding_model(self, model_name: str) -> bool:
        """
        Check whether a model is an embedding model.

        Args:
            model_name: Name of the model to check.

        Returns:
            True if the model is an embedding model, False otherwise.
        """
        ...

    def is_embedding_filter_enabled(self) -> bool:
        """
        Check whether embedding model filtering is currently enabled.

        Returns:
            True if embedding filtering is active, False otherwise.
        """
        ...

    def readiness_verdict(self, mode: RunMode) -> ReadinessVerdict:
        """Return the cached readiness verdict for the given run mode.

        Args:
            mode: The run mode to evaluate readiness for.

        Returns:
            ReadinessVerdict with is_ready, issues, and severity fields.
        """
        ...

    def trigger_readiness_probe(self) -> None:
        """Trigger an async background probe of provider and embedding health."""
        ...

    def subscribe_to_app_readiness_changed(
        self, callback: Callable[[AppReadinessChangedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to app readiness changed events.

        Args:
            callback: Invoked with the new AppReadinessChangedEvent snapshot each time
                the readiness state is re-evaluated.
        """
        ...

    def subscribe_to_provider_registry_reloaded(
        self, callback: Callable[[], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to provider-registry reload events.

        Args:
            callback: Function to invoke when the registry is reloaded.
            parent: Optional QObject whose lifetime governs the subscription.
        """
        ...

    def get_run_names(self, *, exclude_run_id: int | None = None) -> frozenset[str]:
        """Return the case-folded set of existing run names, optionally excluding one run.

        Args:
            exclude_run_id: Optional run ID whose name should be excluded from the result.

        Returns:
            Frozenset of case-folded run name strings.
        """
        ...

    def rename_run(self, *, run_id: int, new_name: str) -> None:
        """Rename a benchmark run and broadcast the change via the event bus.

        Args:
            run_id: Unique ID of the run to rename.
            new_name: The new display name to assign.
        """
        ...
