"""Public factory for the Import/Export Service (`06_IMPORT_FORMATS.md`)."""

import icontract

from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.import_export._internal.service import ImportExportServiceImpl
from ollama_llm_bench.backend.import_export.protocols import ImportExportService
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore

__all__: list[str] = ["make_import_export_service"]


@icontract.require(
    lambda providers_store: providers_store is not None,
    "providers_store must be supplied by compose.py",
)
@icontract.require(
    lambda app_settings_store: app_settings_store is not None,
    "app_settings_store must be supplied by compose.py",
)
@icontract.require(
    lambda event_bus: event_bus is not None, "event_bus must be supplied by compose.py"
)
@icontract.ensure(lambda result: result is not None, "the factory must always return an instance")
def make_import_export_service(
    *,
    providers_store: ProvidersStore,
    app_settings_store: AppSettingsStore,
    event_bus: EventBus,
) -> ImportExportService:
    """Construct the concrete ``ImportExportService`` over the given collaborators.

    Args:
        providers_store: The provider catalog; pre-checked via ``get_by_name``
            during validation and replaced wholesale on a confirmed apply.
        app_settings_store: The user-saved settings layer; merged on a
            confirmed settings apply and read for every export.
        event_bus: The bus on which ``_app_settings_changed`` and
            ``_provider_registry_reloaded`` are emitted after a confirmed apply.

    Returns:
        An ``ImportExportService`` that parses, validates, previews, and
        applies settings-or-provider-config YAML files.
    """
    return ImportExportServiceImpl(
        providers_store=providers_store,
        app_settings_store=app_settings_store,
        event_bus=event_bus,
    )
