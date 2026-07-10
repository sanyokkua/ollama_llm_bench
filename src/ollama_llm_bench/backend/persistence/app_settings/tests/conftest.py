"""Shared fixtures for ``backend/persistence/app_settings/`` colocated tests."""

from collections.abc import Iterator
from pathlib import Path
import sqlite3
import threading

import pytest

from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings.api import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def fake_clock() -> Clock:
    """A deterministic ``Clock`` fixture, fresh per test."""
    return _FakeClock()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """An absolute path to a not-yet-existing database file in ``tmp_path``."""
    return tmp_path / "ollama_llm_bench.db"


@pytest.fixture
def write_conn_and_lock(
    db_path: Path,
) -> Iterator[tuple[sqlite3.Connection, threading.Lock]]:
    """An opened write connection + lock over a fresh ``tmp_path`` database file."""
    conn, lock = open_write_connection(db_path)
    yield conn, lock
    conn.close()


@pytest.fixture
def initialised_write_conn_and_lock(
    db_path: Path,
    write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
    fake_clock: Clock,
) -> tuple[sqlite3.Connection, threading.Lock]:
    """A write connection with the schema already created (first-run DDL applied)."""
    conn, lock = write_conn_and_lock
    ensure_schema(conn, lock, clock=fake_clock)
    return conn, lock


@pytest.fixture
def read_conn_factory(db_path: Path):  # type: ignore[no-untyped-def]
    """A zero-argument callable opening a fresh read-only connection."""

    def _factory() -> sqlite3.Connection:
        return open_read_connection(db_path)

    return _factory
