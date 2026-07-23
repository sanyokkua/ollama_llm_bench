"""Fixtures for the colocated runs-store tests."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.infra.protocols import Clock


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def clock() -> Clock:
    """A deterministic ``Clock`` fixture, fresh per test."""
    return _FakeClock()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """An absolute path to a not-yet-existing database file in ``tmp_path``."""
    return tmp_path / "ollama_llm_bench.db"
