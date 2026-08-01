"""Proves: STORY-067-AC-3

Confirms FakeSettingsGateway records both store-write calls (for asserting the
atomic Save/Reset transaction actually invoked both) and can be scripted to
raise on either write (for the nothing-is-written-on-failure path).
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.ui.settings_dialog.models import (
    SettingsImportPreview,
    SettingsImportResult,
)
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway


def test_replace_providers_and_upsert_settings_calls_are_recorded(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    gateway = FakeSettingsGateway()
    providers = (provider_config_factory(name="Ollama (local)"),)

    gateway.replace_providers(providers)
    gateway.upsert_settings({"ui.theme": "dark"})

    assert gateway.replace_providers_calls == [providers]
    assert gateway.upsert_settings_calls == [{"ui.theme": "dark"}]


def test_scripted_settings_import_preview_and_apply_round_trip() -> None:
    gateway = FakeSettingsGateway()
    preview = SettingsImportPreview(
        rows=(), findings=(), resolved_values={"ui.theme": "dark"}, backend_preview=object()
    )
    result = SettingsImportResult(applied_count=1, skipped_count=0)
    gateway.set_settings_import_preview(preview)
    gateway.set_settings_import_result(result)

    assert gateway.build_settings_import_preview("settings.yaml") is preview
    assert gateway.apply_settings_import(preview) is result


def test_raise_on_next_upsert_settings_raises_once() -> None:
    gateway = FakeSettingsGateway()
    gateway.raise_on_next_upsert_settings(PersistenceError(message="disk full"))

    with pytest.raises(PersistenceError):
        gateway.upsert_settings({"ui.theme": "dark"})

    gateway.upsert_settings({"ui.theme": "light"})  # does not raise a second time
    assert gateway.upsert_settings_calls == [{"ui.theme": "light"}]


def test_save_all_records_both_providers_and_settings_in_one_call(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    """Proves: STORY-067 atomic-Gateway spec-conformance fix.

    ``save_all`` is a single call carrying both the provider catalog and the
    settings values -- the shape that makes true atomicity possible where two
    independent void calls could not.
    """
    gateway = FakeSettingsGateway()
    providers = (provider_config_factory(name="Ollama (local)"),)

    gateway.save_all(providers=providers, settings_values={"ui.theme": "dark"})

    assert gateway.save_all_calls == [(providers, {"ui.theme": "dark"})]
    assert gateway.list_providers() == providers
    assert gateway.get_setting("ui.theme") == "dark"


def test_save_all_failure_leaves_recorded_state_completely_unchanged(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    """Proves: STORY-067 atomic-Gateway spec-conformance fix.

    A scripted ``save_all`` failure mutates neither the provider catalog nor
    the settings map -- true atomicity at the level this Fake can model.
    """
    gateway = FakeSettingsGateway()
    original_providers = (provider_config_factory(name="Ollama (local)"),)
    gateway.set_providers(original_providers)
    gateway.set_setting_value("ui.theme", "system")
    gateway.raise_on_next_save_all(PersistenceError(message="disk full"))

    with pytest.raises(PersistenceError):
        gateway.save_all(
            providers=(provider_config_factory(name="A New Provider"),),
            settings_values={"ui.theme": "dark"},
        )

    assert gateway.save_all_calls == []
    assert gateway.list_providers() == original_providers
    assert gateway.get_setting("ui.theme") == "system"


def test_reset_to_defaults_records_bundled_providers_and_clears_settings(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    """Proves: STORY-067 atomic-Gateway spec-conformance fix.

    ``reset_to_defaults`` replaces the catalog with the bundled providers and
    clears every setting in one call.
    """
    gateway = FakeSettingsGateway()
    gateway.set_setting_value("ui.theme", "dark")
    bundled = (provider_config_factory(name="Ollama (local)"),)

    gateway.reset_to_defaults(bundled_providers=bundled)

    assert gateway.reset_to_defaults_calls == [bundled]
    assert gateway.list_providers() == bundled
    assert gateway.list_settings() == {}


def test_reset_to_defaults_failure_leaves_recorded_state_completely_unchanged(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    """Proves: STORY-067 atomic-Gateway spec-conformance fix.

    A scripted ``reset_to_defaults`` failure mutates neither the provider
    catalog nor the settings map -- true atomicity at the level this Fake can
    model.
    """
    gateway = FakeSettingsGateway()
    original_providers = (provider_config_factory(name="Ollama (local)"),)
    gateway.set_providers(original_providers)
    gateway.set_setting_value("ui.theme", "system")
    gateway.raise_on_next_reset_to_defaults(PersistenceError(message="disk full"))

    with pytest.raises(PersistenceError):
        gateway.reset_to_defaults(bundled_providers=(provider_config_factory(name="LM Studio"),))

    assert gateway.reset_to_defaults_calls == []
    assert gateway.list_providers() == original_providers
    assert gateway.get_setting("ui.theme") == "system"
