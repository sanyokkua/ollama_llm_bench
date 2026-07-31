"""Proves: STORY-067-AC-5

Exercises the real ``SqliteProvidersStore.replace_providers`` transaction that
backs the provider-catalog half of Reset -- both the successful wipe-and-
reseed and the rollback-on-failure path -- against a real ``tmp_path``-backed
SQLite database, independent of whether the cross-store
``SettingsGateway.reset_to_defaults`` exists yet. STORY-110 later adds that
concrete cross-store transaction (``backend.settings.SettingsAtomicWriter``);
see ``test_settings_wipe_now_has_a_real_delete_all_method`` below and the
story's Notes.
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


def test_settings_wipe_now_has_a_real_delete_all_method() -> None:
    """Proves: STORY-067-AC-5

    Supersedes this test's former name and body
    (``test_settings_wipe_has_no_real_delete_all_method_yet``), which
    documented a real gap in ``AppSettingsStore``'s public surface rather than
    fabricating coverage for it. STORY-110 closes that gap: ``AppSettingsStore``
    now also exposes ``replace_all_settings_in_open_transaction`` (delete every
    ``app_settings`` row, then insert every key in the caller's mapping,
    against an already-open transaction) and
    ``upsert_settings_in_open_transaction`` (the same transaction-participating
    shape for the merge-style write), added purely additively alongside the
    four pre-existing methods so ``backend.settings.SettingsAtomicWriter`` can
    compose a real cross-store transaction for
    ``SettingsGateway.save_all``/``reset_to_defaults`` (see
    ``backend/persistence/app_settings/protocols.py`` and this story's Notes).
    The full atomic reset-to-defaults behaviour against a real SQLite-backed
    store (proving every key, including opaque UI-state keys, is re-seeded to
    its in-code default) is STORY-110-AC-4's own designated proof point,
    exercised via a real ``tmp_path``-backed database and
    ``SettingsAtomicWriter`` -- this test only documents the real method
    surface the two new methods now expose.
    """
    public_methods = {
        name
        for name, _ in inspect.getmembers(AppSettingsStore, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {
        "get_setting",
        "upsert_settings",
        "upsert_settings_in_open_transaction",
        "replace_all_settings_in_open_transaction",
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
