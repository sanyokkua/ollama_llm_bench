"""The ``ImportExportService`` implementation (§6, §8, §9).

Wires the four validation/preview builders and the two export assemblers over
``ProvidersStore``/``AppSettingsStore``, and owns the two apply steps: a settings
apply merges only the resolved keys; a provider apply replaces the registry
wholesale with the preview's surviving (``ADDED``) entries (DD-55).
"""

import uuid

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.events.models import (
    SIGNAL_APP_SETTINGS_CHANGED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    AppSettingsChangedEvent,
    ProviderRegistryReloadedEvent,
)
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.import_export._internal.provider_export import export_providers
from ollama_llm_bench.backend.import_export._internal.provider_import import (
    build_provider_import_preview,
)
from ollama_llm_bench.backend.import_export._internal.settings_export import export_settings
from ollama_llm_bench.backend.import_export._internal.settings_import import (
    build_settings_import_preview,
)
from ollama_llm_bench.backend.import_export.models import (
    ImportPreviewGroup,
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportResult,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore

__all__: list[str] = ["ImportExportServiceImpl"]

_EMBEDDING_PROVIDER_NAME_KEY = "embedding.selected_provider_name"
_EMBEDDING_MODEL_NAME_KEY = "embedding.selected_model_name"


class ImportExportServiceImpl:
    """Concrete ``ImportExportService``; see the module docstring for the algorithm."""

    def __init__(
        self,
        *,
        providers_store: ProvidersStore,
        app_settings_store: AppSettingsStore,
        event_bus: EventBus,
    ) -> None:
        self._providers_store = providers_store
        self._app_settings_store = app_settings_store
        self._event_bus = event_bus

    def build_settings_import_preview(self, file_path: str) -> SettingsImportPreview:
        """See ``ImportExportService.build_settings_import_preview``."""
        return build_settings_import_preview(file_path, app_settings_store=self._app_settings_store)

    def apply_settings_import(self, preview: SettingsImportPreview) -> SettingsImportResult:
        """See ``ImportExportService.apply_settings_import``."""
        if preview.resolved_values:
            self._app_settings_store.upsert_settings(dict(preview.resolved_values))
            self._event_bus.emit(
                SIGNAL_APP_SETTINGS_CHANGED,
                AppSettingsChangedEvent(changed_keys=tuple(preview.resolved_values)),
            )
        skipped_count = sum(1 for finding in preview.findings if finding.item_key is not None)
        return SettingsImportResult(
            applied_count=len(preview.resolved_values), skipped_count=skipped_count
        )

    def build_provider_import_preview(self, file_path: str) -> ProviderImportPreview:
        """See ``ImportExportService.build_provider_import_preview``."""
        return build_provider_import_preview(file_path, providers_store=self._providers_store)

    def apply_provider_import(self, preview: ProviderImportPreview) -> ProviderImportResult:
        """See ``ImportExportService.apply_provider_import``."""
        applied: list[ProviderConfig] = []
        skipped_count = 0
        for order, item in enumerate(preview.items):
            if item.group is not ImportPreviewGroup.ADDED or item.draft is None:
                skipped_count += 1
                continue
            draft = item.draft
            applied.append(
                ProviderConfig(
                    provider_id=str(uuid.uuid4()),
                    name=draft.name,
                    provider_type=draft.provider_type,
                    enabled=draft.enabled,
                    base_url=draft.base_url,
                    api_key_raw=draft.api_key_raw,
                    azure_endpoint_raw=draft.azure_endpoint_raw,
                    azure_deployment_raw=draft.azure_deployment_raw,
                    azure_api_version_raw=draft.azure_api_version_raw,
                    default_models=draft.default_models,
                    provider_order=order,
                )
            )
        self._providers_store.replace_providers(tuple(applied))
        self._app_settings_store.upsert_settings(
            {
                _EMBEDDING_PROVIDER_NAME_KEY: preview.embedding_provider_name,
                _EMBEDDING_MODEL_NAME_KEY: preview.embedding_model_name,
            }
        )
        self._event_bus.emit(
            SIGNAL_PROVIDER_REGISTRY_RELOADED,
            ProviderRegistryReloadedEvent(
                provider_count=len(applied),
                enabled_provider_ids=tuple(p.provider_id for p in applied if p.enabled),
                reload_cause="import",
            ),
        )
        return ProviderImportResult(applied_count=len(applied), skipped_count=skipped_count)

    def export_settings(self) -> bytes:
        """See ``ImportExportService.export_settings``."""
        return export_settings(app_settings_store=self._app_settings_store)

    def export_providers(self) -> bytes:
        """See ``ImportExportService.export_providers``."""
        return export_providers(
            providers_store=self._providers_store, app_settings_store=self._app_settings_store
        )
