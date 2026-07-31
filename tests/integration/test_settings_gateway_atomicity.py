"""Proves: STORY-110-AC-3, STORY-110-AC-4

Exercises the real ``SettingsAtomicWriter`` (the collaborator
``SettingsGateway.save_all``/``reset_to_defaults`` delegate to unchanged) against
real ``SqliteProvidersStore``/``SqliteAppSettingsStore`` instances sharing one
``tmp_path``-backed SQLite database and write connection -- proving the real
``BEGIN IMMEDIATE`` / commit / rollback transaction genuinely spans both stores,
not merely two independent best-effort writes in sequence.
"""

from pathlib import Path
import sqlite3
import uuid

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.persistence.app_settings import (
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import create_providers_store
from ollama_llm_bench.backend.settings import DEFAULTS, make_settings_atomic_writer


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-07-31T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


def _make_provider_config(*, name: str) -> ProviderConfig:
    return ProviderConfig(
        provider_id=str(uuid.uuid4()),
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url="http://localhost:11434/v1",
    )


def test_save_all_rolls_back_both_stores_when_the_settings_write_fails(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-110-AC-3

    Given a provider catalog and a settings row set already persisted, and an
    app-settings store whose write raises a persistence error, when
    ``save_all(providers=..., settings_values=...)`` is called with changes to
    both, then the persistence error propagates and both the provider catalog
    and the settings row set still hold their original values -- no partial
    write.
    """
    db_path = tmp_path / "ollama_llm_bench.db"
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=_FakeClock())
    providers_store = create_providers_store(
        write_conn, lock, lambda: open_read_connection(db_path)
    )
    app_settings_store = create_app_settings_store(
        write_conn, lock, lambda: open_read_connection(db_path), _FakeClock()
    )
    original_providers = (_make_provider_config(name="Original"),)
    original_settings = {"benchmark.retry_count": "3"}
    providers_store.replace_providers(original_providers)
    app_settings_store.upsert_settings(original_settings)
    writer = make_settings_atomic_writer(
        write_conn=write_conn,
        lock=lock,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
    )
    mocker.patch.object(
        app_settings_store,
        "upsert_settings_in_open_transaction",
        side_effect=sqlite3.Error("forced failure"),
    )

    with pytest.raises(PersistenceError):
        writer.save_all(
            providers=(_make_provider_config(name="Changed"),),
            settings_values={"benchmark.retry_count": "9"},
        )

    assert providers_store.list_providers() == original_providers
    assert app_settings_store.get_setting("benchmark.retry_count") == "3"


def test_reset_to_defaults_reseeds_every_registry_key_and_the_bundled_providers(
    tmp_path: Path,
) -> None:
    """Proves: STORY-110-AC-4

    Given a configuration in which every settings key has been overridden away
    from its in-code default, when ``reset_to_defaults(bundled_providers=...)``
    is called, then every key in the settings registry's defaults table holds
    its in-code default value again -- including keys the General tab does not
    expose -- and the provider catalog holds exactly the supplied bundled
    providers.
    """
    db_path = tmp_path / "ollama_llm_bench.db"
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=_FakeClock())
    providers_store = create_providers_store(
        write_conn, lock, lambda: open_read_connection(db_path)
    )
    app_settings_store = create_app_settings_store(
        write_conn, lock, lambda: open_read_connection(db_path), _FakeClock()
    )
    overridden = {key: f"not-default-{i}" for i, key in enumerate(DEFAULTS)}
    app_settings_store.upsert_settings(overridden)
    providers_store.replace_providers((_make_provider_config(name="Stale"),))
    writer = make_settings_atomic_writer(
        write_conn=write_conn,
        lock=lock,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
    )
    bundled = (_make_provider_config(name="Ollama (local)"),)

    writer.reset_to_defaults(bundled_providers=bundled, all_default_settings=DEFAULTS)

    assert app_settings_store.list_settings() == dict(DEFAULTS)
    assert app_settings_store.get_setting("ui.window_geometry") == DEFAULTS["ui.window_geometry"]
    assert app_settings_store.get_setting("benchmark.last_mode") == DEFAULTS["benchmark.last_mode"]
    assert providers_store.list_providers() == bundled
