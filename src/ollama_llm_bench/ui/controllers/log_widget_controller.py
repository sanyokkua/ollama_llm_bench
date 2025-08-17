import logging
from typing import Callable

from ollama_llm_bench.core.interfaces import EventBus
from ollama_llm_bench.core.ui_controllers import LogWidgetControllerApi

logger = logging.getLogger(__name__)


class LogWidgetController(LogWidgetControllerApi):
    """
    Controller implementation for managing log display behavior.
    Subscribes to system events and forwards them to log display components.
    """

    def __init__(self, event_bus: EventBus):
        """
        Initialize the log widget controller.

        Args:
            event_bus: Event bus for subscribing to and emitting log-related events.
        """
        self.event_bus = event_bus
        self.event_bus.subscribe_to_background_thread_is_running(self._clean_on_bench_started)

    def _clean_on_bench_started(self, value: bool) -> None:
        """
        Clear logs when a new benchmark execution starts.

        Args:
            value: True if benchmark started, False otherwise.
        """
        logger.debug("Cleaning up benchmark status change")
        if value:
            self.event_bus.emit_log_clean()

    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to log append events to receive new log messages.

        Args:
            callback: Function to invoke with incoming log messages.
        """
        logger.debug("Subscribing to log append")
        self.event_bus.subscribe_to_log_append(callback)

    def subscribe_to_log_clear(self, callback: Callable[[], None]) -> None:
        """
        Subscribe to log clear events to receive requests to clear the log display.

        Args:
            callback: Function to invoke when logs should be cleared.
        """
        logger.debug("Subscribing to log clear")
        self.event_bus.subscribe_to_log_clean(callback)
