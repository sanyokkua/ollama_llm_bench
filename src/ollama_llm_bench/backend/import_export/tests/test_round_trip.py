"""Proves: STORY-038-AC-6 — export/import round-trip guarantee (06_IMPORT_FORMATS.md §9)."""

from pathlib import Path
import string
import uuid

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType, SettingKey
from ollama_llm_bench.backend.import_export._internal.settings_key_catalog import (
    SETTINGS_CATALOG,
    SettingSpec,
    SettingValueType,
)
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeAppSettingsStore,
    FakeProvidersStore,
    make_service,
)

_EMBEDDING_PROVIDER_NAME_KEY = "embedding.selected_provider_name"
_EMBEDDING_MODEL_NAME_KEY = "embedding.selected_model_name"

_PROVIDER_NAME_ALPHABET = string.ascii_lowercase + string.digits + "_"
_MODEL_NAME_ALPHABET = string.ascii_lowercase + string.digits
_ENV_VAR_NAME_STRATEGY = st.from_regex(r"^[A-Za-z_][A-Za-z0-9_]{0,20}$", fullmatch=True)
_PROVIDER_TYPE_STRATEGY = st.sampled_from(
    [ProviderType.OPENAI_COMPATIBLE, ProviderType.ANTHROPIC, ProviderType.GEMINI]
)


def _storage_value_strategy(spec: SettingSpec) -> st.SearchStrategy[str]:
    """Build a Hypothesis strategy of a valid *storage-form* value for one setting spec."""
    if spec.value_type is SettingValueType.BOOL:
        return st.sampled_from(["true", "false"])
    if spec.value_type is SettingValueType.ENUM:
        return st.sampled_from(sorted(spec.enum_values or frozenset()))
    if spec.value_type is SettingValueType.INT:
        int_lo = int(spec.min_value) if spec.min_value is not None else -1_000
        int_hi = int(spec.max_value) if spec.max_value is not None else 1_000
        return st.integers(min_value=int_lo, max_value=int_hi).map(str)
    if spec.value_type is SettingValueType.FLOAT:
        float_lo = spec.min_value if spec.min_value is not None else -1_000.0
        float_hi = spec.max_value if spec.max_value is not None else 1_000.0
        return st.floats(
            min_value=float_lo, max_value=float_hi, allow_nan=False, allow_infinity=False
        ).map(str)
    return st.text(alphabet=_MODEL_NAME_ALPHABET, min_size=0, max_size=10)


_NON_EMBEDDING_SETTING_KEYS = sorted(
    key for key in SETTINGS_CATALOG if not key.startswith("embedding.selected_")
)


@st.composite
def _settings_dict_strategy(draw: st.DrawFn) -> dict[SettingKey, str]:
    """Draw a subset of non-embedding-selection catalog keys with valid storage values.

    The two ``embedding.selected_*`` keys are excluded here because the test
    itself controls them directly (they carry the embedding selection under
    test, set from ``providers[0].name`` plus a fixed model name).
    """
    keys = draw(
        st.lists(st.sampled_from(_NON_EMBEDDING_SETTING_KEYS), min_size=1, max_size=6, unique=True)
    )
    return {key: draw(_storage_value_strategy(SETTINGS_CATALOG[key])) for key in keys}


@st.composite
def _provider_strategy(draw: st.DrawFn, *, name: str, order: int) -> ProviderConfig:
    provider_type = draw(_PROVIDER_TYPE_STRATEGY)
    is_openai = provider_type is ProviderType.OPENAI_COMPATIBLE
    base_url = "http://localhost:11434/v1" if is_openai else None
    api_key = draw(st.one_of(st.just(""), _ENV_VAR_NAME_STRATEGY))
    enabled = draw(st.booleans())
    default_models = tuple(
        draw(
            st.lists(
                st.text(alphabet=_MODEL_NAME_ALPHABET, min_size=1, max_size=12),
                max_size=3,
                unique=True,
            )
        )
    )
    optional_text = st.one_of(
        st.none(), st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12)
    )
    azure_endpoint = draw(optional_text) if is_openai else None
    azure_deployment = draw(optional_text) if is_openai else None
    azure_api_version = draw(optional_text) if is_openai else None
    return ProviderConfig(
        provider_id=str(uuid.uuid4()),
        name=name,
        provider_type=provider_type,
        enabled=enabled,
        base_url=base_url,
        api_key_raw=api_key or None,
        azure_endpoint_raw=azure_endpoint,
        azure_deployment_raw=azure_deployment,
        azure_api_version_raw=azure_api_version,
        default_models=default_models,
        provider_order=order,
    )


@st.composite
def _providers_strategy(draw: st.DrawFn) -> tuple[ProviderConfig, ...]:
    names = draw(
        st.lists(
            st.text(alphabet=_PROVIDER_NAME_ALPHABET, min_size=1, max_size=16),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    return tuple(
        draw(_provider_strategy(name=name, order=order)) for order, name in enumerate(names)
    )


@pytest.mark.slow
@given(settings_values=_settings_dict_strategy(), providers=_providers_strategy())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_export_import_is_value_preserving(
    tmp_path: Path, settings_values: dict[SettingKey, str], providers: tuple[ProviderConfig, ...]
) -> None:
    """Proves: STORY-038-AC-6

    For a settings store and a provider registry drawn from their full valid
    domains, exporting then reimporting leaves every exported setting at its
    exported value and reproduces the same provider list by name, type,
    base_url, enabled, default_models, Azure fields, and api_key value form,
    plus the same embedding selection by name+model — while provider_id is
    regenerated fresh, never round-tripped.
    """
    embedding_provider_name = providers[0].name
    embedding_model_name = "embed-model"
    source_settings_store = FakeAppSettingsStore(
        initial_values={
            **settings_values,
            _EMBEDDING_PROVIDER_NAME_KEY: embedding_provider_name,
            _EMBEDDING_MODEL_NAME_KEY: embedding_model_name,
        }
    )
    source_providers_store = FakeProvidersStore(providers=providers)
    source_service = make_service(
        providers_store=source_providers_store, app_settings_store=source_settings_store
    )

    settings_bytes = source_service.export_settings()
    providers_bytes = source_service.export_providers()
    settings_path = tmp_path / "settings_export.yaml"
    settings_path.write_bytes(settings_bytes)
    providers_path = tmp_path / "providers_export.yaml"
    providers_path.write_bytes(providers_bytes)

    dest_settings_store = FakeAppSettingsStore()
    dest_providers_store = FakeProvidersStore()
    dest_service = make_service(
        providers_store=dest_providers_store, app_settings_store=dest_settings_store
    )
    dest_service.apply_settings_import(
        dest_service.build_settings_import_preview(str(settings_path))
    )
    dest_service.apply_provider_import(
        dest_service.build_provider_import_preview(str(providers_path))
    )

    assert all(
        dest_settings_store.get_setting(key) == value for key, value in settings_values.items()
    )
    assert dest_settings_store.get_setting(_EMBEDDING_PROVIDER_NAME_KEY) == embedding_provider_name
    assert dest_settings_store.get_setting(_EMBEDDING_MODEL_NAME_KEY) == embedding_model_name

    dest_by_name = {provider.name: provider for provider in dest_providers_store.list_providers()}
    assert dest_by_name.keys() == {provider.name for provider in providers}
    assert all(
        (
            dest_by_name[provider.name].provider_type,
            dest_by_name[provider.name].base_url,
            dest_by_name[provider.name].enabled,
            dest_by_name[provider.name].default_models,
            dest_by_name[provider.name].azure_endpoint_raw,
            dest_by_name[provider.name].azure_deployment_raw,
            dest_by_name[provider.name].azure_api_version_raw,
            dest_by_name[provider.name].api_key_raw,
        )
        == (
            provider.provider_type,
            provider.base_url,
            provider.enabled,
            provider.default_models,
            provider.azure_endpoint_raw,
            provider.azure_deployment_raw,
            provider.azure_api_version_raw,
            provider.api_key_raw,
        )
        for provider in providers
    )
    assert all(
        dest_by_name[provider.name].provider_id != provider.provider_id for provider in providers
    )
