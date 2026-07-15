"""Proves: STORY-038-AC-7 — no writes on hard error or non-confirmation (06_IMPORT_FORMATS.md §8)."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeAppSettingsStore,
    FakeProvidersStore,
    make_provider_config,
    make_service,
    write_yaml_mapping,
    write_yaml_text,
)


def test_hard_error_or_cancel_writes_nothing(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-7

    Given any import, when a file-level hard error is present, then no store
    write occurs on either store — covers EC-IMP-11 at the service boundary.
    """
    providers_store = FakeProvidersStore()
    settings_store = FakeAppSettingsStore()
    service = make_service(providers_store=providers_store, app_settings_store=settings_store)
    file_path = write_yaml_text(tmp_path, "kind: settings\nsettings: {}\n", name="import.txt")

    with pytest.raises(TaskFileError):
        service.build_settings_import_preview(file_path)

    assert providers_store.replace_calls == []
    assert settings_store.upsert_calls == []


def test_unconfirmed_preview_leaves_state_unchanged(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-7

    Given the user does not confirm the preview (``apply_settings_import`` is
    simply never called), then nothing is applied and the current state is
    unchanged.
    """
    providers_store = FakeProvidersStore(providers=(make_provider_config(name="existing"),))
    settings_store = FakeAppSettingsStore(initial_values={"ui.theme": "light"})
    service = make_service(providers_store=providers_store, app_settings_store=settings_store)
    file_path = write_yaml_mapping(
        tmp_path, {"kind": "settings", "schema_version": 1, "settings": {"ui.theme": "dark"}}
    )

    service.build_settings_import_preview(file_path)

    assert settings_store.get_setting("ui.theme") == "light"
    assert settings_store.upsert_calls == []
    assert {provider.name for provider in providers_store.list_providers()} == {"existing"}
    assert providers_store.replace_calls == []
