"""``FakeSettingsGateway`` -- an in-memory test double for ``ui/settings_dialog/``'s
``SettingsGateway`` swap point (STORY-066, extended by STORY-067).

No real I/O; the provider catalog, settings, and probe results are held in plain
Python containers and are externally settable by a test. Mirrors the
fake-construction pattern already used by ``ui.new_benchmark.testing``'s
``FakeNewBenchmarkGateway``. STORY-067 adds call-tracking lists for the two
Save/Reset write methods (so a test can assert the atomic transaction actually
invoked both) plus scriptable fakes for the six Import/Export methods.

``save_all``/``reset_to_defaults`` (spec-conformance amendment) model
atomicity the same way ``replace_providers``/``upsert_settings`` already do: a
scripted raise (``raise_on_next_save_all``/``raise_on_next_reset_to_defaults``)
fires *before* any state mutation, so a test can assert the Fake's recorded
state is completely unchanged on a scripted failure. ``replace_providers`` and
``upsert_settings`` are kept as separately callable methods -- Import still
calls ``upsert_settings`` via ``apply_settings_import`` -- but Save/Reset now
call only the two new atomic methods.
"""

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from ollama_llm_bench.ui.settings_dialog.models import (
        ProviderImportPreview,
        ProviderImportResult,
        SettingsImportPreview,
        SettingsImportResult,
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
        replace_providers_calls: Every ``configs`` tuple passed to a
            successful ``replace_providers`` call, in call order (STORY-067) --
            a scripted raise (``raise_on_next_replace_providers``) is not
            recorded, matching the real store's all-or-nothing write.
        upsert_settings_calls: Every ``values`` dict passed to a successful
            ``upsert_settings`` call (including via ``apply_settings_import``),
            in call order (STORY-067); a scripted raise is not recorded.
        save_all_calls: Every ``(providers, settings_values)`` pair passed to
            a successful ``save_all`` call, in call order; a scripted raise
            (``raise_on_next_save_all``) is not recorded and mutates no state.
        reset_to_defaults_calls: Every ``bundled_providers`` tuple passed to a
            successful ``reset_to_defaults`` call, in call order; a scripted
            raise (``raise_on_next_reset_to_defaults``) is not recorded and
            mutates no state.
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
        self.replace_providers_calls: list[tuple[ProviderConfig, ...]] = []
        self.upsert_settings_calls: list[dict[SettingKey, str]] = []
        self.save_all_calls: list[tuple[tuple[ProviderConfig, ...], dict[SettingKey, str]]] = []
        self.reset_to_defaults_calls: list[tuple[ProviderConfig, ...]] = []
        self._raise_on_next_replace_providers: Exception | None = None
        self._raise_on_next_upsert_settings: Exception | None = None
        self._raise_on_next_save_all: Exception | None = None
        self._raise_on_next_reset_to_defaults: Exception | None = None
        self._settings_import_preview: SettingsImportPreview | None = None
        self._provider_import_preview: ProviderImportPreview | None = None
        self._settings_import_result: SettingsImportResult | None = None
        self._provider_import_result: ProviderImportResult | None = None
        self._export_settings_bytes: bytes = b""
        self._export_providers_bytes: bytes = b""

    def build_settings_import_preview(self, file_path: str) -> "SettingsImportPreview":  # noqa: ARG002  # canned fake: path unused by design
        if self._settings_import_preview is None:
            raise RuntimeError("call set_settings_import_preview first")
        return self._settings_import_preview

    def apply_settings_import(self, preview: "SettingsImportPreview") -> "SettingsImportResult":
        self.upsert_settings_calls.append(dict(preview.resolved_values))
        self._settings.update(preview.resolved_values)
        if self._settings_import_result is None:
            raise RuntimeError("call set_settings_import_result first")
        return self._settings_import_result

    def build_provider_import_preview(self, file_path: str) -> "ProviderImportPreview":  # noqa: ARG002  # canned fake: path unused by design
        if self._provider_import_preview is None:
            raise RuntimeError("call set_provider_import_preview first")
        return self._provider_import_preview

    def apply_provider_import(self, preview: "ProviderImportPreview") -> "ProviderImportResult":  # noqa: ARG002  # canned fake: preview unused by design
        if self._provider_import_result is None:
            raise RuntimeError("call set_provider_import_result first")
        return self._provider_import_result

    def export_settings(self) -> bytes:
        return self._export_settings_bytes

    def export_providers(self) -> bytes:
        return self._export_providers_bytes

    def set_settings_import_preview(self, preview: "SettingsImportPreview") -> None:
        """Test helper: script ``build_settings_import_preview``'s return value."""
        self._settings_import_preview = preview

    def set_provider_import_preview(self, preview: "ProviderImportPreview") -> None:
        """Test helper: script ``build_provider_import_preview``'s return value."""
        self._provider_import_preview = preview

    def set_settings_import_result(self, result: "SettingsImportResult") -> None:
        """Test helper: script ``apply_settings_import``'s return value."""
        self._settings_import_result = result

    def set_provider_import_result(self, result: "ProviderImportResult") -> None:
        """Test helper: script ``apply_provider_import``'s return value."""
        self._provider_import_result = result

    def set_export_settings_bytes(self, payload: bytes) -> None:
        """Test helper: script ``export_settings``'s return value."""
        self._export_settings_bytes = payload

    def set_export_providers_bytes(self, payload: bytes) -> None:
        """Test helper: script ``export_providers``'s return value."""
        self._export_providers_bytes = payload

    def raise_on_next_replace_providers(self, exc: Exception) -> None:
        """Test helper: make the next ``replace_providers`` call raise ``exc``."""
        self._raise_on_next_replace_providers = exc

    def raise_on_next_upsert_settings(self, exc: Exception) -> None:
        """Test helper: make the next ``upsert_settings`` call raise ``exc``."""
        self._raise_on_next_upsert_settings = exc

    def raise_on_next_save_all(self, exc: Exception) -> None:
        """Test helper: make the next ``save_all`` call raise ``exc`` before
        mutating any state."""
        self._raise_on_next_save_all = exc

    def raise_on_next_reset_to_defaults(self, exc: Exception) -> None:
        """Test helper: make the next ``reset_to_defaults`` call raise ``exc``
        before mutating any state."""
        self._raise_on_next_reset_to_defaults = exc

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return self._providers

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        return next((p for p in self._providers if p.name == name), None)

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        if self._raise_on_next_replace_providers is not None:
            exc, self._raise_on_next_replace_providers = (
                self._raise_on_next_replace_providers,
                None,
            )
            raise exc
        self.replace_providers_calls.append(configs)
        self._providers = configs

    def get_setting(self, key: SettingKey) -> str | None:
        return self._settings.get(key)

    def list_settings(self) -> dict[SettingKey, str]:
        return dict(self._settings)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        if self._raise_on_next_upsert_settings is not None:
            exc, self._raise_on_next_upsert_settings = self._raise_on_next_upsert_settings, None
            raise exc
        self.upsert_settings_calls.append(dict(values))
        self._settings.update(values)

    def get_resolved_str(self, key: SettingKey) -> str:
        return self._settings.get(key, "")

    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None:
        if self._raise_on_next_save_all is not None:
            exc, self._raise_on_next_save_all = self._raise_on_next_save_all, None
            raise exc
        self.save_all_calls.append((providers, dict(settings_values)))
        self._providers = providers
        self._settings.update(settings_values)

    def reset_to_defaults(self, *, bundled_providers: tuple[ProviderConfig, ...]) -> None:
        if self._raise_on_next_reset_to_defaults is not None:
            exc, self._raise_on_next_reset_to_defaults = self._raise_on_next_reset_to_defaults, None
            raise exc
        self.reset_to_defaults_calls.append(bundled_providers)
        self._providers = bundled_providers
        self._settings = {}

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
