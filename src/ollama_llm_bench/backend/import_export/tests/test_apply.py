"""Proves: STORY-038-AC-5 — confirmed-apply merge/replace semantics (06_IMPORT_FORMATS.md §8)."""

from ollama_llm_bench.backend.domain import ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.import_export.models import (
    ImportPreviewGroup,
    ProviderImportItem,
    ProviderImportPreview,
    SettingsImportPreview,
)
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeAppSettingsStore,
    FakeProvidersStore,
    make_provider_config,
    make_service,
)


def test_provider_import_apply_replaces_registry_wholesale() -> None:
    """Proves: STORY-038-AC-5

    Given a confirmed provider-config import, when it is applied, then the
    provider registry is replaced wholesale by the imported set — a
    pre-existing provider not present in the import is gone afterward.
    """
    providers_store = FakeProvidersStore(providers=(make_provider_config(name="old_provider"),))
    service = make_service(providers_store=providers_store)
    draft = ProviderConfigDraft(
        name="new_provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url="http://localhost:11434/v1",
    )
    preview = ProviderImportPreview(
        items=(
            ProviderImportItem(name="new_provider", group=ImportPreviewGroup.ADDED, draft=draft),
        ),
        embedding_provider_name="new_provider",
        embedding_model_name="embed-model",
        findings=(),
    )

    service.apply_provider_import(preview)

    assert {provider.name for provider in providers_store.list_providers()} == {"new_provider"}


def test_settings_import_apply_merges_only_present_keys() -> None:
    """Proves: STORY-038-AC-5

    Given a confirmed settings import, when it is applied, then only the
    present valid keys are written — every other setting keeps its current
    value.
    """
    settings_store = FakeAppSettingsStore(
        initial_values={"ui.theme": "light", "benchmark.retry_count": "1"}
    )
    service = make_service(app_settings_store=settings_store)
    preview = SettingsImportPreview(items=(), findings=(), resolved_values={"ui.theme": "dark"})

    service.apply_settings_import(preview)

    assert settings_store.get_setting("ui.theme") == "dark"
    assert settings_store.get_setting("benchmark.retry_count") == "1"


def test_settings_import_apply_with_no_resolved_values_writes_nothing() -> None:
    """Proves: STORY-038-AC-5

    A confirmed settings-import preview with an empty resolved-values map
    (every key was skipped during validation) writes nothing at all.
    """
    settings_store = FakeAppSettingsStore(initial_values={"ui.theme": "light"})
    service = make_service(app_settings_store=settings_store)
    preview = SettingsImportPreview(items=(), findings=(), resolved_values={})

    result = service.apply_settings_import(preview)

    assert settings_store.upsert_calls == []
    assert result.applied_count == 0
