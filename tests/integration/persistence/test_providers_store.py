"""Integration tests for ``backend/persistence/providers/``.

Exercises the real ``ProvidersStore`` public surface — ``create_providers_store`` and
the ``SqliteProvidersStore`` it returns — against a real ``tmp_path`` SQLite database
file, never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-012 acceptance criteria AC-1, AC-2, AC-3, AC-4.
"""

from pathlib import Path
import sqlite3
import uuid

import pytest

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import ProvidersStore, create_providers_store

_UUID_VERSION_4 = 4
_UPDATED_PROVIDER_ORDER = 5


@pytest.fixture
def providers_store(db_path: Path, clock: Clock) -> tuple[ProvidersStore, sqlite3.Connection]:
    """A ``ProvidersStore`` wired over a fresh ``tmp_path`` database, plus the write
    connection.

    The write connection is returned alongside the store so tests can execute raw
    SQL against the same physical database the store writes through (asserting
    cascade behaviour and simulating already-committed run-history rows).
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    store = create_providers_store(write_conn, lock, lambda: open_read_connection(db_path))
    return store, write_conn


def _make_draft(
    *,
    name: str = "My Provider",
    base_url: str | None = "http://localhost:11434/v1",
    default_models: tuple[str, ...] = ("llama3", "mistral"),
    provider_order: int = 0,
) -> ProviderConfigDraft:
    """Build a placeholder ``ProviderConfigDraft`` for ``add`` calls."""
    return ProviderConfigDraft(
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url=base_url,
        default_models=default_models,
        provider_order=provider_order,
    )


def test_add_generates_uuid4_and_returns_it_after_commit(
    providers_store: tuple[ProvidersStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-012-AC-1

    Given an empty provider catalog, when add(draft) is called, then the store
    generates a fresh UUID4 textual provider_id, inserts the providers row and
    its provider_models rows in one transaction, and returns the generated
    provider_id only after commit.
    """
    store, write_conn = providers_store
    draft = _make_draft()

    # Sanity: nothing committed before the call.
    rows_before = write_conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    assert rows_before == 0

    # Act
    new_provider_id = store.add(draft)

    # Assert — the id is a well-formed UUID4 textual representation.
    parsed = uuid.UUID(new_provider_id)
    assert parsed.version == _UUID_VERSION_4

    # Assert — the row and its model children are committed and readable.
    committed = write_conn.execute(
        "SELECT name, provider_type, enabled, base_url, provider_order FROM providers "
        "WHERE provider_id = ?",
        (new_provider_id,),
    ).fetchone()
    assert committed == ("My Provider", "openai_compatible", 1, "http://localhost:11434/v1", 0)
    model_rows = write_conn.execute(
        "SELECT model_name FROM provider_models WHERE provider_id = ? ORDER BY model_order",
        (new_provider_id,),
    ).fetchall()
    assert [row[0] for row in model_rows] == ["llama3", "mistral"]

    # Assert — the store round-trips the same provider through get_by_name.
    fetched = store.get_by_name("My Provider")
    assert fetched is not None
    assert fetched.provider_id == new_provider_id
    assert fetched.default_models == ("llama3", "mistral")


def test_duplicate_name_raises_atomically_and_get_by_name_precheck(
    providers_store: tuple[ProvidersStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-012-AC-2

    Given a provider named N already exists, when add attempts to persist a
    second row named N, then the store raises PersistenceError and no
    half-applied row survives; get_by_name(N) returns the existing provider
    before the attempt.
    """
    store, write_conn = providers_store
    store.add(_make_draft(name="Duplicate Name"))

    # Assert — the friendly-error pre-check finds the existing row.
    existing = store.get_by_name("Duplicate Name")
    assert existing is not None
    assert existing.name == "Duplicate Name"

    rows_before = write_conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    models_before = write_conn.execute("SELECT COUNT(*) FROM provider_models").fetchone()[0]

    # Act / Assert — the UNIQUE(name) backstop raises atomically on add.
    with pytest.raises(PersistenceError):
        store.add(_make_draft(name="Duplicate Name", default_models=("other-model",)))

    rows_after = write_conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    models_after = write_conn.execute("SELECT COUNT(*) FROM provider_models").fetchone()[0]
    assert rows_after == rows_before
    assert models_after == models_before

    # Act / Assert — the same backstop raises atomically on update targeting a
    # different row.
    other_id = store.add(_make_draft(name="Other Provider"))
    other_config = store.get_by_name("Other Provider")
    assert other_config is not None
    renamed = ProviderConfig(
        provider_id=other_config.provider_id,
        name="Duplicate Name",
        provider_type=other_config.provider_type,
        enabled=other_config.enabled,
        base_url=other_config.base_url,
        default_models=other_config.default_models,
        provider_order=other_config.provider_order,
    )
    with pytest.raises(PersistenceError):
        store.update(other_id, renamed)

    # Assert — the other row's name is untouched by the failed update.
    unchanged = store.get_by_name("Other Provider")
    assert unchanged is not None
    assert unchanged.provider_id == other_id


def test_update_preserves_immutable_provider_id(
    providers_store: tuple[ProvidersStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-012-AC-3

    Given a persisted provider, when update is called with a changed name and
    model list, then every column except provider_id is updated on that row
    and the provider_id is unchanged.
    """
    store, _write_conn = providers_store
    provider_id = store.add(_make_draft(name="Before Name", default_models=("model-a",)))
    before = store.get_by_name("Before Name")
    assert before is not None

    changed = ProviderConfig(
        provider_id=before.provider_id,
        name="After Name",
        provider_type=before.provider_type,
        enabled=False,
        base_url="http://localhost:9999/v1",
        default_models=("model-b", "model-c"),
        provider_order=_UPDATED_PROVIDER_ORDER,
    )

    # Act
    store.update(provider_id, changed)

    # Assert — the row is found by its new name, with the same provider_id.
    after = store.get_by_name("After Name")
    assert after is not None
    assert after.provider_id == provider_id
    assert after.name == "After Name"
    assert after.enabled is False
    assert after.base_url == "http://localhost:9999/v1"
    assert after.default_models == ("model-b", "model-c")
    assert after.provider_order == _UPDATED_PROVIDER_ORDER

    # Assert — the old name no longer resolves.
    assert store.get_by_name("Before Name") is None


def test_delete_cascades_models_and_caps_but_preserves_run_snapshot(
    providers_store: tuple[ProvidersStore, sqlite3.Connection],
) -> None:
    """Proves: STORY-012-AC-4

    Given a persisted provider with provider_models and model_capabilities rows
    and a past run whose snapshot references it, when delete is called, then
    the provider and its provider_models and model_capabilities rows are
    removed while the run's frozen snapshot rows survive and remain readable.
    """
    store, write_conn = providers_store
    provider_id = store.add(_make_draft(name="Doomed Provider", default_models=("model-a",)))

    # Arrange — a cached capability row for this provider.
    write_conn.execute(
        "INSERT INTO model_capabilities "
        "(provider_id, model_name, capability, supported, last_observed_at, observed_via) "
        "VALUES (?, 'model-a', 'streaming', 1, '2026-01-01T00:00:00+00:00', 'probe')",
        (provider_id,),
    )

    # Arrange — a run whose frozen snapshot references this provider by id, per
    # DD-33 (the link is logical, not a declared FK, so it must survive deletion).
    write_conn.execute(
        "INSERT INTO benchmark_runs "
        "(run_id, timestamp, run_mode, status, total_tasks, completed_tasks, "
        "total_elapsed_ms, schema_version, created_at) "
        "VALUES (1, '2026-01-01T00:00:00+00:00', 'tasks', 'completed', 1, 1, 100, 1, "
        "'2026-01-01T00:00:00+00:00')"
    )
    write_conn.execute(
        "INSERT INTO benchmark_run_providers "
        "(run_id, provider_id, name, provider_type, base_url) "
        "VALUES (1, ?, 'Doomed Provider', 'openai_compatible', 'http://localhost:11434/v1')",
        (provider_id,),
    )
    write_conn.commit()

    # Sanity — the child rows exist before delete.
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM provider_models WHERE provider_id = ?", (provider_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM model_capabilities WHERE provider_id = ?", (provider_id,)
        ).fetchone()[0]
        == 1
    )

    # Act
    store.delete(provider_id)

    # Assert — the provider and its live-catalog children are gone.
    assert store.get_by_name("Doomed Provider") is None
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM provider_models WHERE provider_id = ?", (provider_id,)
        ).fetchone()[0]
        == 0
    )
    assert (
        write_conn.execute(
            "SELECT COUNT(*) FROM model_capabilities WHERE provider_id = ?", (provider_id,)
        ).fetchone()[0]
        == 0
    )

    # Assert — the run's frozen snapshot row survives deletion and remains readable.
    snapshot_row = write_conn.execute(
        "SELECT provider_id, name FROM benchmark_run_providers WHERE run_id = 1"
    ).fetchone()
    assert snapshot_row == (provider_id, "Doomed Provider")
