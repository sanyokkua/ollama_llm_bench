"""``FakeNewBenchmarkGateway`` -- an in-memory ``NewBenchmarkGateway`` test double.

No real I/O; settings are held in a plain dict, providers are whatever
``set_providers`` configures. Mirrors the fake-construction pattern already used by
``backend.task_files.testing.FakeTaskFileLoader``.
"""

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderConfig,
    ReadinessState,
    RunId,
    RunStartRequest,
    SettingKey,
)

__all__: list[str] = ["FakeNewBenchmarkGateway"]

_DEFAULT_READINESS = AppReadinessSnapshot(
    overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
)


class FakeNewBenchmarkGateway:
    """An in-memory ``NewBenchmarkGateway`` with externally settable state.

    Attributes:
        recorded_set_settings: Every ``(key, value)`` pair passed to ``set_setting``,
            in call order -- lets a test assert persistence without a real store.
        recorded_start_run_requests: Every ``RunStartRequest`` passed to ``start_run``
            (unused by this story; present for STORY-055 reuse).
    """

    def __init__(self) -> None:
        self._settings: dict[str, str] = {}
        self._providers: tuple[ProviderConfig, ...] = ()
        self._readiness: AppReadinessSnapshot = _DEFAULT_READINESS
        self.recorded_set_settings: list[tuple[str, str]] = []
        self.recorded_start_run_requests: list[RunStartRequest] = []

    def get_setting(self, key: SettingKey) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        self._settings[key] = value
        self.recorded_set_settings.append((key, value))

    def provider_list(self) -> tuple[ProviderConfig, ...]:
        return self._providers

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def start_run(self, request: RunStartRequest) -> RunId:
        self.recorded_start_run_requests.append(request)
        return 1

    def set_setting_value(self, key: SettingKey, value: str) -> None:
        """Test helper: seed a setting as if it had been previously persisted."""
        self._settings[key] = value

    def set_providers(self, providers: tuple[ProviderConfig, ...]) -> None:
        """Test helper: force ``provider_list()``'s return value."""
        self._providers = providers

    def set_readiness(self, snapshot: AppReadinessSnapshot) -> None:
        """Test helper: force ``readiness_snapshot()``'s return value."""
        self._readiness = snapshot
