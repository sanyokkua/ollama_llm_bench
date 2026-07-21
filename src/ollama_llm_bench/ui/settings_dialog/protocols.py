"""``SettingsGateway`` Protocol (D-R-06), declared verbatim per 08-E §7b.6.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.6. All 13 methods are declared here even though this story's controller and
sub-dialog call only 8 of them (``list_providers``, ``get_provider_by_name``,
``test_provider``, ``discover_models``, ``probe_all``, ``readiness_snapshot``, plus
the read-only ``get_setting``/``list_settings`` a later story wires into the
General tab) -- STORY-067 (General tab, Save/Import/Reset) uses
``replace_providers``/``upsert_settings``/``get_resolved_str``/
``list_model_capabilities``/``upsert_model_capability``/``probe_embedding`` without
re-touching this file.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    InferenceTestResult,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderId,
    SettingKey,
)

__all__: list[str] = ["SettingsGateway"]


class SettingsGateway(Protocol):
    """Adapter gateway for the Settings Dialog (D-R-06)."""

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Read the provider catalog for the Providers tab.

        fast-synchronous.
        """
        ...

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        """Look up a provider by display name for live duplicate-name validation.

        fast-synchronous.
        """
        ...

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically (Save / Import / Reset).

        blocking.
        """
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read one user-saved setting, including the embedding selection keys
        (``embedding.selected_provider_name`` / ``embedding.selected_model_name``).

        fast-synchronous.
        """
        ...

    def list_settings(self) -> dict[SettingKey, str]:
        """Read the full user-saved settings row set for the working copy.

        fast-synchronous.
        """
        ...

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Write several settings atomically (the settings half of Save / Reset).

        blocking.
        """
        ...

    def get_resolved_str(self, key: SettingKey) -> str:
        """Resolve the current effective value of a general-tab key (initial copy).

        fast-synchronous.
        """
        ...

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Read cached capability records for a model (capability hints).

        fast-synchronous.
        """
        ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Persist a user-overridden capability record.

        blocking.
        """
        ...

    def test_provider(self, provider_id: ProviderId, model_name: ModelName) -> InferenceTestResult:
        """Run the per-row Test-connection inference probe for a provider/model.

        blocking; acquires the ``PROVIDER_TEST`` single-inference gate.
        """
        ...

    def discover_models(self, provider_id: ProviderId) -> tuple[ModelName, ...]:
        """Discover a provider's models for the embedding-section picker.

        blocking.
        """
        ...

    def probe_all(self) -> AppReadinessSnapshot:
        """Run the auto-check on open; emits readiness-changed.

        blocking.
        """
        ...

    def probe_embedding(self) -> AppReadinessSnapshot:
        """Run the Test-Embedding probe behind the embedding section.

        blocking; acquires the ``PROVIDER_TEST`` single-inference gate.
        """
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Read the current snapshot for the Health Dots.

        fast-synchronous.
        """
        ...
