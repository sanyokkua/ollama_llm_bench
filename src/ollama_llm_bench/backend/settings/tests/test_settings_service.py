"""Unit tests for ``SettingsServiceImpl`` — unknown keys, malformed values, upsert.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8 (the ``ConfigurationError``-on-unknown-key rule and the SPEC-110
coercion-failure rule).
"""

import pytest
import structlog.testing

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry
from ollama_llm_bench.backend.errors import ConfigurationError, ProgrammerError
from ollama_llm_bench.backend.events import SIGNAL_APP_SETTINGS_CHANGED, AppSettingsChangedEvent
from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS
from ollama_llm_bench.backend.settings.api import make_settings_service
from ollama_llm_bench.backend.settings.tests.conftest import (
    FakeAppSettingsStore,
    FakeEventBus,
    make_benchmark_run,
)

_UNKNOWN_KEY = "not.a.registry.key"


def test_unknown_key_raises_configuration_error_without_side_effects() -> None:
    """Proves: STORY-014-AC-3

    Given a key that is not present in the DEFAULTS map, when a typed accessor
    or set/upsert is called with that key, then it raises ConfigurationError
    and performs no read fall-through and no write — the fake store's write
    method is never called and no event is emitted.
    """
    # Arrange
    store = FakeAppSettingsStore()
    event_bus = FakeEventBus()
    service = make_settings_service(store=store, event_bus=event_bus)

    # Act / Assert — every accessor and every write entry point rejects the unknown key.
    with pytest.raises(ConfigurationError):
        service.get_str(_UNKNOWN_KEY)
    with pytest.raises(ConfigurationError):
        service.get_bool(_UNKNOWN_KEY)
    with pytest.raises(ConfigurationError):
        service.get_int(_UNKNOWN_KEY)
    with pytest.raises(ConfigurationError):
        service.get_float(_UNKNOWN_KEY)
    with pytest.raises(ConfigurationError):
        service.set(_UNKNOWN_KEY, "value")
    with pytest.raises(ConfigurationError):
        service.upsert({_UNKNOWN_KEY: "value"})

    assert store.upsert_calls == []
    assert event_bus.emitted == []


def test_upsert_with_one_unknown_key_among_known_keys_writes_nothing() -> None:
    """Proves: STORY-014-AC-3

    An unknown key anywhere in a multi-key upsert call aborts the whole call
    before any write — even the known keys in the same call are not written.
    """
    # Arrange
    store = FakeAppSettingsStore()
    event_bus = FakeEventBus()
    service = make_settings_service(store=store, event_bus=event_bus)

    # Act
    with pytest.raises(ConfigurationError):
        service.upsert({"ui.theme": "dark", _UNKNOWN_KEY: "value"})

    # Assert
    assert store.upsert_calls == []
    assert event_bus.emitted == []


def test_malformed_user_value_falls_through_to_default_and_logs_a_warning() -> None:
    """Proves: STORY-014-AC-4

    Given a user-saved value that cannot be coerced to the accessor's
    requested type, when the typed accessor reads it, then it returns the
    key's in-code default, logs a warning naming the key, and does not raise.
    """
    # Arrange
    key = "benchmark.warmup_enabled"
    store = FakeAppSettingsStore(initial_values={key: "not-a-bool"})
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    with structlog.testing.capture_logs() as captured_logs:
        resolved = service.get_bool(key)

    # Assert
    assert resolved == (DEFAULTS[key] == "true")
    warning_logs = [entry for entry in captured_logs if entry["log_level"] == "warning"]
    assert len(warning_logs) == 1
    assert warning_logs[0]["event"] == "setting_coercion_failed"
    assert warning_logs[0]["key"] == key


def test_malformed_snapshot_value_raises_programmer_error() -> None:
    """Proves: STORY-014-AC-4

    Given a per-run snapshot value that cannot be coerced, the accessor raises
    a ProgrammerError — snapshots are app-written from validated input and
    cannot legitimately be malformed.
    """
    # Arrange
    key = "benchmark.retry_count"
    run = make_benchmark_run(
        settings_snapshot=(BenchmarkRunSettingEntry(setting_key=key, setting_value="not-an-int"),)
    )
    store = FakeAppSettingsStore()
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act / Assert
    with pytest.raises(ProgrammerError):
        service.get_int(key, run=run)


def test_upsert_writes_atomically_and_emits_settings_changed_with_changed_keys() -> None:
    """Proves: STORY-014-AC-5

    Given a set of setting values, when upsert writes them, then the values
    are written to the user-saved layer atomically (exactly one
    upsert_settings call with the full mapping) and exactly one
    _app_settings_changed event is emitted carrying the set of changed keys —
    the keys passed to upsert, not a diff against prior values.
    """
    # Arrange
    store = FakeAppSettingsStore()
    event_bus = FakeEventBus()
    service = make_settings_service(store=store, event_bus=event_bus)
    values = {"ui.theme": "dark", "benchmark.retry_count": "5"}

    # Act
    service.upsert(values)

    # Assert
    assert store.upsert_calls == [values]
    assert len(event_bus.emitted) == 1
    signal_name, payload = event_bus.emitted[0]
    assert signal_name == SIGNAL_APP_SETTINGS_CHANGED
    assert payload == AppSettingsChangedEvent(changed_keys=tuple(values))


def test_upsert_changed_keys_is_not_a_diff_against_prior_values() -> None:
    """Proves: STORY-014-AC-5

    Re-upserting a key with the value it already holds still reports that key
    in changed_keys — the event carries the keys passed to upsert, not a diff
    computed against the previous stored value.
    """
    # Arrange
    store = FakeAppSettingsStore(initial_values={"ui.theme": "dark"})
    event_bus = FakeEventBus()
    service = make_settings_service(store=store, event_bus=event_bus)

    # Act
    service.upsert({"ui.theme": "dark"})

    # Assert
    _, payload = event_bus.emitted[0]
    assert payload == AppSettingsChangedEvent(changed_keys=("ui.theme",))
