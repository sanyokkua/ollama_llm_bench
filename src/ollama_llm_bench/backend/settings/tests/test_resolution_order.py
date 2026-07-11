"""Proves the resolution-order cascade holds over every key (STORY-014-AC-2).

The Phase-level resolution-order-correctness property test: for every registry key
and every combination of layer presence, the first present layer in cascade order
wins — ``Per-Run Snapshot -> User-Saved -> Default`` for a per-run-overridable key
read with a run, ``User-Saved -> Default`` (skipping the snapshot) otherwise.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``
§2.
"""

from hypothesis import given, strategies as st

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry
from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings.api import make_settings_service
from ollama_llm_bench.backend.settings.tests.conftest import (
    FakeAppSettingsStore,
    FakeEventBus,
    make_benchmark_run,
)

_ALL_KEYS = tuple(sorted(DEFAULTS))
_SNAPSHOT_VALUE = "__snapshot_value__"
_USER_SAVED_VALUE = "__user_saved_value__"


@given(
    key=st.sampled_from(_ALL_KEYS),
    has_snapshot_value=st.booleans(),
    has_run=st.booleans(),
    has_user_saved_value=st.booleans(),
)
def test_resolution_returns_first_present_layer_in_order(
    key: str, *, has_snapshot_value: bool, has_run: bool, has_user_saved_value: bool
) -> None:
    """Proves: STORY-014-AC-2

    Invariant (Hypothesis over every registry key x every layer-presence
    combination): resolving a key always yields the value of the first present
    layer in cascade order. A per-run-overridable key is only ever resolved at
    the snapshot layer when it is BOTH per-run-overridable AND read with a run
    that carries a snapshot entry for it; a non-overridable key's snapshot
    entry — even if adversarially present on the run — is never consulted;
    absent every higher layer, the in-code default always wins.
    """
    # Arrange
    is_overridable = key in PER_RUN_OVERRIDABLE
    snapshot_entries = (
        (BenchmarkRunSettingEntry(setting_key=key, setting_value=_SNAPSHOT_VALUE),)
        if has_snapshot_value
        else ()
    )
    run = make_benchmark_run(settings_snapshot=snapshot_entries) if has_run else None
    initial_values = {key: _USER_SAVED_VALUE} if has_user_saved_value else {}
    store = FakeAppSettingsStore(initial_values=initial_values)
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_str(key, run=run)

    # Assert
    snapshot_layer_applies = is_overridable and has_run and has_snapshot_value
    if snapshot_layer_applies:
        assert resolved == _SNAPSHOT_VALUE
    elif has_user_saved_value:
        assert resolved == _USER_SAVED_VALUE
    else:
        assert resolved == DEFAULTS[key]


@given(key=st.sampled_from(sorted(PER_RUN_OVERRIDABLE)))
def test_run_none_skips_snapshot_layer_even_for_overridable_key(key: str) -> None:
    """Proves: STORY-014-AC-2

    Invariant (Hypothesis over every per-run-overridable key): reading with
    ``run=None`` always resolves ``User-Saved -> Default``, never a snapshot —
    there is no run to consult, so a would-be snapshot value can never leak in.
    """
    # Arrange
    store = FakeAppSettingsStore(initial_values={key: _USER_SAVED_VALUE})
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_str(key, run=None)

    # Assert
    assert resolved == _USER_SAVED_VALUE


@given(key=st.sampled_from(tuple(sorted(DEFAULTS.keys() - PER_RUN_OVERRIDABLE))))
def test_non_overridable_key_never_resolves_from_an_adversarial_snapshot(key: str) -> None:
    """Proves: STORY-014-AC-2

    Invariant (Hypothesis over every non-overridable key): even when a run's
    snapshot adversarially carries an entry for a non-overridable key, that
    value is never consulted — resolution falls through to
    ``User-Saved -> Default`` exactly as if ``run`` were ``None``.
    """
    # Arrange
    snapshot_entries = (BenchmarkRunSettingEntry(setting_key=key, setting_value=_SNAPSHOT_VALUE),)
    run = make_benchmark_run(settings_snapshot=snapshot_entries)
    store = FakeAppSettingsStore(initial_values={key: _USER_SAVED_VALUE})
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_str(key, run=run)

    # Assert
    assert resolved == _USER_SAVED_VALUE
