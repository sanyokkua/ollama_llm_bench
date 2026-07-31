"""Shared fixtures and local test doubles for ``backend/settings/`` tests.

``backend/settings/testing.py`` exports fakes of *this module's own Protocols*
(``FakeSettingsService``/``FakeRunSnapshotBuilder``) for *downstream* consumers — they
would be circular to use for testing this module itself. These tests instead need a
fake of this module's collaborator Protocol (``AppSettingsStore``) and a minimal
``BenchmarkRun`` factory, both defined locally here.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    BenchmarkRunSettingEntry,
    RunMode,
    RunStatus,
    SettingKey,
)
from ollama_llm_bench.backend.events.protocols import Subscription


class FakeAppSettingsStore:
    """A minimal in-memory ``AppSettingsStore`` double.

    Args:
        initial_values: Seed values for the user-saved layer.
    """

    def __init__(self, *, initial_values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(initial_values or {})
        self.upsert_calls: list[dict[SettingKey, str]] = []

    def get_setting(self, key: SettingKey) -> str | None:
        """Return the stored value for ``key``, or ``None`` if unset."""
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Record the call and write every value into the in-memory layer."""
        self.upsert_calls.append(dict(values))
        self._values.update(values)

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        """Test double: same effect as ``upsert_settings``, no transaction semantics."""
        self.upsert_settings(values)

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        """Test double: wipe and re-seed the in-memory layer with ``values``."""
        self._values = dict(values)

    def list_settings(self) -> dict[SettingKey, str]:
        """Return every stored key/value pair."""
        return dict(self._values)

    def get_schema_version(self) -> int:
        """Return a fixed schema version; unused by settings resolution."""
        return 1


class FakeEventBus:
    """A minimal in-memory ``EventBus`` double recording every ``emit`` call."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        """Unused by these tests; present only to satisfy the Protocol shape."""
        raise NotImplementedError("subscribe is not exercised by backend/settings tests")

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emitted ``(signal_name, payload)`` pair."""
        self.emitted.append((signal_name, payload))


def make_benchmark_run(
    *, settings_snapshot: tuple[BenchmarkRunSettingEntry, ...] = ()
) -> BenchmarkRun:
    """Build a minimal, otherwise-arbitrary ``BenchmarkRun`` carrying a snapshot.

    Args:
        settings_snapshot: The frozen per-run setting entries to attach.

    Returns:
        A ``BenchmarkRun`` with placeholder values for every field the
        settings-resolution cascade does not consult.
    """
    return BenchmarkRun(
        run_id=1,
        run_name="test-run",
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=0,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        settings_snapshot=settings_snapshot,
    )


@pytest.fixture
def fake_store() -> FakeAppSettingsStore:
    """A fresh in-memory ``AppSettingsStore`` double with no seeded values."""
    return FakeAppSettingsStore()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    """A fresh in-memory ``EventBus`` double."""
    return FakeEventBus()
