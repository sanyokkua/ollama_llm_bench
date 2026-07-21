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
    preview = SettingsImportPreview(rows=(), findings=(), resolved_values={"ui.theme": "dark"})
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
