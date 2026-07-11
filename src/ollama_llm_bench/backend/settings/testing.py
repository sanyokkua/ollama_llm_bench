"""Fakes implementing ``SettingsService`` and ``RunSnapshotBuilder`` for downstream tests.

These fakes hold an in-memory user-saved layer (no SQLite, no event bus) and apply the
same registry/cascade rules as the concrete implementations, so a downstream module's
tests can exercise settings-dependent code without wiring real persistence.
"""

from ollama_llm_bench.backend.domain import BenchmarkRun, SettingKey
from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings._internal.resolver import (
    coerce_bool,
    coerce_float,
    coerce_int,
    require_known_key,
)
from ollama_llm_bench.backend.settings.models import BenchmarkRunSettingEntry, RunSettingsSnapshot

__all__: list[str] = [
    "FakeRunSnapshotBuilder",
    "FakeSettingsService",
]


class FakeSettingsService:
    """An in-memory ``SettingsService`` fake backed by a plain dict.

    Args:
        initial_values: Seed values for the user-saved layer, keyed by
            registry key. Every key must already be a member of the registry.
    """

    def __init__(self, *, initial_values: dict[SettingKey, str] | None = None) -> None:
        self._saved: dict[SettingKey, str] = dict(initial_values or {})
        self.emitted_changed_keys: list[tuple[str, ...]] = []

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        """Resolve a string setting from the fake's in-memory layers."""
        require_known_key(key)
        raw, _ = self._resolve_raw(key, run)
        return raw

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        """Resolve a boolean setting from the fake's in-memory layers."""
        require_known_key(key)
        raw, _ = self._resolve_raw(key, run)
        return coerce_bool(raw)

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        """Resolve an integer setting from the fake's in-memory layers."""
        require_known_key(key)
        raw, _ = self._resolve_raw(key, run)
        return coerce_int(raw)

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        """Resolve a float setting from the fake's in-memory layers."""
        require_known_key(key)
        raw, _ = self._resolve_raw(key, run)
        return coerce_float(raw)

    def set(self, key: SettingKey, value: str) -> None:
        """Write one value and record the emitted changed-keys tuple."""
        require_known_key(key)
        self._saved[key] = value
        self.emitted_changed_keys.append((key,))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        """Write several values atomically and record the emitted changed-keys tuple."""
        for key in values:
            require_known_key(key)
        self._saved.update(values)
        self.emitted_changed_keys.append(tuple(values))

    def _resolve_raw(self, key: SettingKey, run: BenchmarkRun | None) -> tuple[str, bool]:
        if key in PER_RUN_OVERRIDABLE and run is not None:
            for entry in run.settings_snapshot:
                if entry.setting_key == key:
                    return entry.setting_value, True
        if key in self._saved:
            return self._saved[key], False
        return DEFAULTS[key], False


class FakeRunSnapshotBuilder:
    """An in-memory ``RunSnapshotBuilder`` fake.

    Args:
        settings_service: A ``FakeSettingsService`` (or compatible object)
            whose user-saved layer supplies each per-run-overridable key's
            ``User-Saved -> Default`` value.
    """

    def __init__(self, *, settings_service: FakeSettingsService) -> None:
        self._settings_service = settings_service

    def build_snapshot(self) -> RunSettingsSnapshot:
        """Capture every per-run-overridable key from the fake settings service."""
        return tuple(
            BenchmarkRunSettingEntry(
                setting_key=key,
                setting_value=self._settings_service.get_str(key, run=None),
            )
            for key in sorted(PER_RUN_OVERRIDABLE)
        )
