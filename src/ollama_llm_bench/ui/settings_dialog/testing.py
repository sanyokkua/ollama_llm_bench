"""``FakeSettingsGateway`` -- an in-memory test double for ``ui/settings_dialog/``'s
``SettingsGateway`` swap point (STORY-066).

No real I/O; the provider catalog, settings, and probe results are held in plain
Python containers and are externally settable by a test. Mirrors the
fake-construction pattern already used by ``ui.new_benchmark.testing``'s
``FakeNewBenchmarkGateway``.
"""

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    InferenceTestOutcome,
    InferenceTestResult,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderId,
    ReadinessState,
    SettingKey,
)

__all__: list[str] = ["FakeSettingsGateway"]

_DEFAULT_READINESS = AppReadinessSnapshot(
    overall=ReadinessState.READY, per_provider=(), embedding_reachable=False
)


class FakeSettingsGateway:
    """An in-memory ``SettingsGateway`` with externally settable state.

    Attributes:
        recorded_test_provider_calls: Every ``(provider_id, model_name)`` pair
            passed to ``test_provider``, in call order.
        recorded_probe_all_calls: The count of ``probe_all()`` calls.
        recorded_probe_embedding_calls: The count of ``probe_embedding()`` calls.
        recorded_discover_models_calls: Every ``provider_id`` passed to
            ``discover_models``, in call order.
    """

    def __init__(self) -> None:
        self._providers: tuple[ProviderConfig, ...] = ()
        self._settings: dict[SettingKey, str] = {}
        self._readiness: AppReadinessSnapshot = _DEFAULT_READINESS
        self._test_provider_result: InferenceTestResult | None = None
        self._discovered_models: dict[ProviderId, tuple[ModelName, ...]] = {}
        self.recorded_test_provider_calls: list[tuple[str, str]] = []
        self.recorded_probe_all_calls = 0
        self.recorded_probe_embedding_calls = 0
        self.recorded_discover_models_calls: list[str] = []

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return self._providers

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        return next((p for p in self._providers if p.name == name), None)

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        self._providers = configs

    def get_setting(self, key: SettingKey) -> str | None:
        return self._settings.get(key)

    def list_settings(self) -> dict[SettingKey, str]:
        return dict(self._settings)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        self._settings.update(values)

    def get_resolved_str(self, key: SettingKey) -> str:
        return self._settings.get(key, "")

    def list_model_capabilities(
        self,
        provider_id: ProviderId,  # noqa: ARG002  # canned fake: unused by design
        model_name: ModelName,  # noqa: ARG002  # canned fake: unused by design
    ) -> tuple[ModelCapabilityRecord, ...]:
        return ()

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:  # noqa: ARG002  # canned fake: unused by design
        return None

    def test_provider(self, provider_id: ProviderId, model_name: ModelName) -> InferenceTestResult:
        self.recorded_test_provider_calls.append((provider_id, model_name))
        if self._test_provider_result is not None:
            return self._test_provider_result
        return InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=provider_id,
            model_name=model_name or "unknown",
            latency_ms=10,
            tested_at=0,
        )

    def discover_models(self, provider_id: ProviderId) -> tuple[ModelName, ...]:
        self.recorded_discover_models_calls.append(provider_id)
        return self._discovered_models.get(provider_id, ())

    def probe_all(self) -> AppReadinessSnapshot:
        self.recorded_probe_all_calls += 1
        return self._readiness

    def probe_embedding(self) -> AppReadinessSnapshot:
        self.recorded_probe_embedding_calls += 1
        return self._readiness

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def set_providers(self, providers: tuple[ProviderConfig, ...]) -> None:
        """Test helper: force ``list_providers()``'s return value."""
        self._providers = providers

    def set_setting_value(self, key: SettingKey, value: str) -> None:
        """Test helper: seed a setting as if it had been previously persisted."""
        self._settings[key] = value

    def set_readiness(self, snapshot: AppReadinessSnapshot) -> None:
        """Test helper: force ``probe_all``/``readiness_snapshot``'s return value."""
        self._readiness = snapshot

    def set_test_provider_result(self, result: InferenceTestResult | None) -> None:
        """Test helper: force ``test_provider``'s return value."""
        self._test_provider_result = result

    def set_discovered_models(self, provider_id: ProviderId, models: tuple[ModelName, ...]) -> None:
        """Test helper: seed ``discover_models``'s return value for one provider."""
        self._discovered_models[provider_id] = models
