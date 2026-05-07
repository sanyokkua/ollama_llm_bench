"""ProviderHealthRunnable — QRunnable wrapper for non-blocking provider health checks."""

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker


class _Signals(QObject):
    completed: Signal = Signal(object)


class ProviderHealthRunnable(QRunnable):
    """Runs a ProviderHealthChecker on a background thread and emits the result."""

    def __init__(
        self,
        *,
        provider: LLMProviderApi,
        checker: ProviderHealthChecker,
    ) -> None:
        super().__init__()
        self.signals = _Signals()
        self._provider = provider
        self._checker = checker

    @Slot()
    def run(self) -> None:
        result: HealthCheckResult = self._checker.check(self._provider)
        self.signals.completed.emit(result)
