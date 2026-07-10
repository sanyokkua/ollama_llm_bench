"""Integration test proving the single-writer connection serializes concurrent writes.

Source of truth: STORY-008 acceptance criterion AC-5 and
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §2.1
(Connection topology, DD-41).
"""

from pathlib import Path
import threading

from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)


def test_concurrent_writes_are_serialized_through_one_lock(db_path: Path, clock: Clock) -> None:
    """Proves: STORY-008-AC-5

    Given a write issued through the single-writer connection, when a second
    write is issued concurrently from another thread, then the two writes are
    serialized through the one lock, each runs in its own BEGIN IMMEDIATE
    transaction synchronously on its calling thread, and neither observes the
    other half-applied — the committed database contains both writes intact.
    """
    # Arrange
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        store = create_app_settings_store(
            write_conn, lock, lambda: open_read_connection(db_path), clock
        )
        thread_one = threading.Thread(
            target=store.upsert_settings, args=({"writer.one": "value-one"},)
        )
        thread_two = threading.Thread(
            target=store.upsert_settings, args=({"writer.two": "value-two"},)
        )

        # Act
        thread_one.start()
        thread_two.start()
        thread_one.join(timeout=10)
        thread_two.join(timeout=10)

        # Assert
        assert not thread_one.is_alive()
        assert not thread_two.is_alive()
        settings = store.list_settings()
        assert settings["writer.one"] == "value-one"
        assert settings["writer.two"] == "value-two"
    finally:
        write_conn.close()
