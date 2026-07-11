"""Unit test for ``RunSnapshotBuilderImpl.build_snapshot`` (STORY-014-AC-6).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``
§5; ``08-E_interfaces_contracts.md`` §8a.
"""

from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings.api import make_run_snapshot_builder
from ollama_llm_bench.backend.settings.tests.conftest import FakeAppSettingsStore


def test_build_snapshot_captures_exactly_the_per_run_overridable_keys() -> None:
    """Proves: STORY-014-AC-6

    When build_snapshot() is called, then the returned frozen tuple contains
    exactly one BenchmarkRunSettingEntry for every key in PER_RUN_OVERRIDABLE
    — no more and no fewer — each carrying that key's User-Saved -> Default
    resolved value, and no key outside PER_RUN_OVERRIDABLE appears in the
    snapshot.
    """
    # Arrange
    user_saved_overrides = {key: f"override::{key}" for key in sorted(PER_RUN_OVERRIDABLE)[:3]}
    store = FakeAppSettingsStore(initial_values=user_saved_overrides)
    builder = make_run_snapshot_builder(store=store)

    # Act
    snapshot = builder.build_snapshot()

    # Assert: exactly one entry per PER_RUN_OVERRIDABLE key, no more, no fewer.
    snapshot_keys = tuple(entry.setting_key for entry in snapshot)
    assert len(snapshot) == len(PER_RUN_OVERRIDABLE)
    assert len(set(snapshot_keys)) == len(snapshot_keys)
    assert set(snapshot_keys) == PER_RUN_OVERRIDABLE

    # Assert: no key outside PER_RUN_OVERRIDABLE appears.
    assert set(snapshot_keys).isdisjoint(DEFAULTS.keys() - PER_RUN_OVERRIDABLE)

    # Assert: each entry carries its User-Saved -> Default resolved value.
    resolved_by_key = {entry.setting_key: entry.setting_value for entry in snapshot}
    for key in PER_RUN_OVERRIDABLE:
        expected = user_saved_overrides.get(key, DEFAULTS[key])
        assert resolved_by_key[key] == expected
