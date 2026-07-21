"""Proves: STORY-067-AC-5

Exercises the real ``SqliteProvidersStore.replace_providers`` transaction that
backs the provider-catalog half of Reset -- both the successful wipe-and-
reseed and the rollback-on-failure path -- against a real ``tmp_path``-backed
SQLite database, independent of whether the cross-store
``SettingsGateway.reset_to_defaults`` exists yet (it does not; see
``test_settings_wipe_has_no_real_delete_all_method_yet`` below and the
story's Notes).
"""

import inspect
from pathlib import Path
import uuid

import pytest

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.persistence.app_settings import (
    AppSettingsStore,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import ProvidersStore, create_providers_store
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

_BUNDLED_PROVIDER_SEEDS: tuple[tuple[str, str], ...] = (
    ("Ollama (local)", "http://localhost:11434/v1"),
    ("LM Studio (local)", "http://localhost:1234/v1"),
    ("llama.cpp (local)", "http://localhost:8080/v1"),
)


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


def _bundled_default_provider_configs() -> tuple[ProviderConfig, ...]:
    return tuple(
        ProviderConfig(
            provider_id=str(uuid.uuid4()),
            name=name,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url=base_url,
            enabled=False,
        )
        for name, base_url in _BUNDLED_PROVIDER_SEEDS
    )


def _open_real_providers_store(tmp_path: Path) -> ProvidersStore:
    db_path = tmp_path / "ollama_llm_bench.db"
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=_FakeClock())
    return create_providers_store(write_conn, lock, lambda: open_read_connection(db_path))


def test_reset_replace_providers_wipes_and_reseeds_atomically(tmp_path: Path) -> None:
    """Proves: STORY-067-AC-5

    Given a custom provider persisted through the real store, when the
    provider-catalog half of the Reset transaction runs
    (``ProvidersStore.replace_providers`` with the three bundled providers),
    then the catalog holds exactly those three and nothing else -- proving
    the real store's wipe-then-reseed behaviour.
    """
    providers_store = _open_real_providers_store(tmp_path)
    providers_store.add(
        ProviderConfigDraft(
            name="Custom Provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            enabled=True,
            base_url="https://api.openai.com/v1",
        )
    )

    providers_store.replace_providers(_bundled_default_provider_configs())

    names = {p.name for p in providers_store.list_providers()}
    assert names == {"Ollama (local)", "LM Studio (local)", "llama.cpp (local)"}


def test_reset_replace_providers_rolls_back_on_constraint_violation(tmp_path: Path) -> None:
    """Proves: STORY-067-AC-5

    Forces a real ``UNIQUE (name)`` constraint violation partway through the
    reseed batch (two rows sharing a name) and asserts
    ``replace_providers`` raises ``PersistenceError`` while leaving the
    catalog exactly as it was before the call -- proving the real
    ``BEGIN IMMEDIATE`` / rollback transaction is genuinely all-or-nothing,
    not merely a sequential best-effort delete-then-insert.
    """
    providers_store = _open_real_providers_store(tmp_path)
    providers_store.add(
        ProviderConfigDraft(
            name="Custom Provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            enabled=True,
            base_url="https://api.openai.com/v1",
        )
    )
    prior = providers_store.list_providers()
    colliding_name = "Ollama (local)"
    colliding_configs = (
        ProviderConfig(
            provider_id=str(uuid.uuid4()),
            name=colliding_name,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="http://localhost:11434/v1",
            enabled=False,
        ),
        ProviderConfig(
            provider_id=str(uuid.uuid4()),
            name=colliding_name,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="http://localhost:1234/v1",
            enabled=False,
        ),
    )

    with pytest.raises(PersistenceError):
        providers_store.replace_providers(colliding_configs)

    assert providers_store.list_providers() == prior


def test_settings_wipe_has_no_real_delete_all_method_yet() -> None:
    """Proves: STORY-067-AC-5

    Documents, rather than fabricates, real-store coverage for the
    settings-wipe half of Reset. ``AppSettingsStore``
    (``backend/persistence/app_settings/protocols.py``) exposes only
    ``get_setting``/``upsert_settings`` (a merge-style write),
    ``list_settings``, and ``get_schema_version`` -- there is no "delete
    every row" method to integration-test against a real SQLite-backed store
    yet. Building a real-store test for the settings half here would either
    call a method that does not exist, or silently pass while asserting
    nothing about wiping opaque keys (``ui.window_geometry``,
    ``benchmark.last_mode``, etc.) -- exactly the false-confidence gap the
    second spec-conformance review flagged.

    ``SettingsGateway.reset_to_defaults``'s own docstring
    (``ui/settings_dialog/protocols.py``) commits the concrete Phase 11
    adapter to wiping every ``app_settings`` row and re-seeding the full
    in-code defaults table in one atomic transaction alongside the
    provider-catalog wipe proven above by
    ``test_reset_replace_providers_wipes_and_reseeds_atomically``. That
    commitment is proven today only at the level this module can prove it: a
    scripted-failure unit test against ``FakeSettingsGateway`` --
    ``ui/settings_dialog/tests/test_fake_gateway.py::
    test_reset_to_defaults_failure_leaves_recorded_state_completely_unchanged``
    -- which asserts a failed ``reset_to_defaults`` call mutates neither the
    provider catalog nor the settings map. This test instead asserts the real
    ``AppSettingsStore`` Protocol's current public surface has no delete-all
    method, so this documented gap is caught the day one is added and this
    test (and its story Notes) should be revisited.
    """
    public_methods = {
        name
        for name, _ in inspect.getmembers(AppSettingsStore, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {
        "get_setting",
        "upsert_settings",
        "list_settings",
        "get_schema_version",
    }


def test_reset_to_defaults_protocol_commits_to_wiping_every_settings_row() -> None:
    """Proves: STORY-067-AC-5

    Asserts the ``SettingsGateway.reset_to_defaults`` Protocol method's own
    docstring commits the concrete Phase 11 adapter to wiping every
    ``app_settings`` row (not merely the General tab's own registry keys) and
    re-seeding the in-code defaults table -- the contract this UI module
    hands downstream, verified textually since the concrete implementation
    does not exist yet to verify behaviourally.
    """
    docstring = inspect.getdoc(SettingsGateway.reset_to_defaults) or ""
    assert "app_settings" in docstring
    assert "every" in docstring
    assert "re-seeds" in docstring
