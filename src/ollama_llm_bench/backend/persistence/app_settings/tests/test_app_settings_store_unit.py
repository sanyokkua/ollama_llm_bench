"""Unit tests for ``SqliteAppSettingsStore`` (colocated; real tmp_path SQLite files).

Source of truth: STORY-008 acceptance criterion AC-6.
"""

from collections.abc import Callable
import sqlite3
import threading

from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings.api import create_app_settings_store
from ollama_llm_bench.backend.persistence.app_settings.models import EXPECTED_SCHEMA_VERSION


def test_upsert_and_get_setting_round_trips_a_written_key(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    read_conn_factory: Callable[[], sqlite3.Connection],
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-6

    A key written via upsert_settings is read back with the same value via
    get_setting.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    store = create_app_settings_store(conn, lock, read_conn_factory, fake_clock)

    # Act
    store.upsert_settings({"ui.theme": "dark"})
    value = store.get_setting("ui.theme")

    # Assert
    assert value == "dark"


def test_get_setting_returns_none_for_an_unwritten_key(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    read_conn_factory: Callable[[], sqlite3.Connection],
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-6

    An unwritten setting key returns None from get_setting, never raises.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    store = create_app_settings_store(conn, lock, read_conn_factory, fake_clock)

    # Act
    value = store.get_setting("ui.never_set")

    # Assert
    assert value is None


def test_list_settings_returns_every_written_key(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    read_conn_factory: Callable[[], sqlite3.Connection],
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-6

    list_settings returns every key/value pair written via upsert_settings, in
    one atomic multi-key write.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    store = create_app_settings_store(conn, lock, read_conn_factory, fake_clock)

    # Act
    store.upsert_settings({"ui.theme": "dark", "benchmark.retry_count": "3"})
    settings = store.list_settings()

    # Assert
    assert settings == {"ui.theme": "dark", "benchmark.retry_count": "3"}


def test_upsert_settings_updates_an_existing_key(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    read_conn_factory: Callable[[], sqlite3.Connection],
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-6

    Upserting the same key twice overwrites the stored value rather than
    raising a uniqueness error.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    store = create_app_settings_store(conn, lock, read_conn_factory, fake_clock)
    store.upsert_settings({"ui.theme": "dark"})

    # Act
    store.upsert_settings({"ui.theme": "light"})

    # Assert
    assert store.get_setting("ui.theme") == "light"


def test_get_schema_version_returns_the_stored_integer(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    read_conn_factory: Callable[[], sqlite3.Connection],
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-6

    get_schema_version returns the integer stored in app_meta.schema_version.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    store = create_app_settings_store(conn, lock, read_conn_factory, fake_clock)

    # Act
    version = store.get_schema_version()

    # Assert
    assert version == EXPECTED_SCHEMA_VERSION
