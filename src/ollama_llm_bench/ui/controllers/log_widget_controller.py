import logging
from typing import Callable

from ollama_llm_bench.core.controllers import LogWidgetControllerApi
from ollama_llm_bench.core.interfaces import EventBus

logger = logging.getLogger(__name__)


class LogWidgetController(LogWidgetControllerApi):
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.event_bus.subscribe_to_background_thread_is_running(self._clean_on_bench_started)

    def _clean_on_bench_started(self, value: bool) -> None:
        logger.debug("Cleaning up benchmark status change")
        if value:
            self.event_bus.emit_log_clean()

    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        logger.debug("Subscribing to log append")
        self.event_bus.subscribe_to_log_append(callback)

    def subscribe_to_log_clear(self, callback: Callable[[], None]) -> None:
        logger.debug("Subscribing to log clear")
        self.event_bus.subscribe_to_log_clean(callback)
