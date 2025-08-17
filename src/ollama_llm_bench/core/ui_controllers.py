from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from ollama_llm_bench.core.models import AvgSummaryTableItem, NewRunWidgetStartEvent, SummaryTableItem


class PreviousRunWidgetControllerApi(ABC):
    """
    Controller interface for handling PreviousRunWidget events and state updates.
    """

    @abstractmethod
    def handle_refresh_click(self, _) -> None:
        """
        Handle the refresh button click event.
        """

    @abstractmethod
    def handle_start_click(self, _) -> None:
        """
        Handle the start benchmark button click event.
        """

    @abstractmethod
    def handle_stop_click(self, _) -> None:
        """
        Handle the stop benchmark button click event.
        """

    @abstractmethod
    def handle_item_change(self, run_id: Optional[int]) -> None:
        """
        Handle the dropdown item change event.

        Args:
            run_id: Selected run ID, or None if no selection.
        """

    @abstractmethod
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        """
        Subscribe to run id change events.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_runs_change(self, callback: Callable[[List[tuple[int, str]]], None]) -> None:
        """
        Subscribe to runs list change events.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """

    @abstractmethod
    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to benchmark status change events.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """


class NewRunWidgetControllerApi(ABC):
    """
    Controller interface for handling NewRunWidget events and state updates.
    """

    @abstractmethod
    def handle_refresh_click(self, _) -> None:
        """
        Handle the refresh button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_start_click(self, event: NewRunWidgetStartEvent) -> None:
        """
        Handle the start benchmark button click event by emitting the appropriate event.

        Args:
            event: Event object containing judge model and test models.
        """

    @abstractmethod
    def handle_stop_click(self, _) -> None:
        """
        Handle the stop benchmark button click event by emitting the appropriate event.
        """

    @abstractmethod
    def subscribe_to_models_change(self, callback: Callable[[List[str]], None]) -> None:
        """
        Subscribe to models list change events to update the dropdown and list.

        Args:
            callback: Function to invoke with updated list of model names.
        """

    @abstractmethod
    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to benchmark status change events to update UI state.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """


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
    def handle_run_selection_change(self, run_id: Optional[int]) -> None:
        """
        Handle the run selection dropdown change event by emitting the appropriate event.

        Args:
            run_id: Newly selected run ID, or None if deselected.
        """

    @abstractmethod
    def handle_delete_click(self, _) -> None:
        """
        Handle the delete button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_summary_export_csv_click(self, _) -> None:
        """
        Handle the summary CSV export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_summary_export_md_click(self, _) -> None:
        """
        Handle the summary Markdown export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_detailed_export_csv_click(self, _) -> None:
        """
        Handle the detailed CSV export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def handle_detailed_export_md_click(self, _) -> None:
        """
        Handle the detailed Markdown export button click event by emitting the appropriate event.
        """

    @abstractmethod
    def subscribe_to_runs_change(self, callback: Callable[[List[tuple[int, str]]], None]) -> None:
        """
        Subscribe to runs list change events to populate the dropdown.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """

    @abstractmethod
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        """
        Subscribe to run id change events.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_summary_data_change(self, callback: Callable[[List[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to summary data change events to update the summary table.

        Args:
            callback: Function to invoke with new summary table data.
        """

    @abstractmethod
    def subscribe_to_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
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
