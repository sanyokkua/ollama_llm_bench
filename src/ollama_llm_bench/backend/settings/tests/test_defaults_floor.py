"""Proves the ``DEFAULTS`` map is a total floor over the registry (STORY-014-AC-1).

Also carries a plain registry-invariant sanity check: ``PER_RUN_OVERRIDABLE`` is a
subset of ``DEFAULTS``'s keys, as called out explicitly in the story.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``
§2-3 and ``08-G_feature_flags.md`` §3-9.
"""

from hypothesis import given, strategies as st

from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings._internal.resolver import coerce_bool, coerce_int
from ollama_llm_bench.backend.settings.api import make_settings_service
from ollama_llm_bench.backend.settings.tests.conftest import FakeAppSettingsStore, FakeEventBus

_BOOL_KEYS = frozenset(key for key, raw in DEFAULTS.items() if raw in ("true", "false"))
_INT_KEYS = frozenset(
    key for key, raw in DEFAULTS.items() if key not in _BOOL_KEYS and raw.lstrip("-").isdigit()
)


@given(key=st.sampled_from(sorted(DEFAULTS)))
def test_default_layer_is_total_over_registry(key: str) -> None:
    """Proves: STORY-014-AC-1

    Invariant (Hypothesis over every registry key): given no user-saved value and no
    run, ``get_str`` resolves the key's declared default string exactly, and never
    raises absence. This alone proves the default layer is a total floor over the
    string-typed view of the registry, which is sufficient because every other typed
    accessor is defined as ``str`` resolution followed by coercion of the same raw
    value (`_internal/resolver.py::resolve_typed`).
    """
    # Arrange
    store = FakeAppSettingsStore()
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_str(key, run=None)

    # Assert
    assert resolved == DEFAULTS[key]


@given(key=st.sampled_from(sorted(_BOOL_KEYS)))
def test_default_layer_bool_keys_resolve_without_raising(key: str) -> None:
    """Proves: STORY-014-AC-1

    Invariant (Hypothesis over every bool-typed registry key): ``get_bool`` resolves
    the declared default with no user-saved value and no run, coercing successfully
    and never raising.
    """
    # Arrange
    store = FakeAppSettingsStore()
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_bool(key, run=None)

    # Assert
    assert resolved == coerce_bool(DEFAULTS[key])


@given(key=st.sampled_from(sorted(_INT_KEYS)))
def test_default_layer_int_keys_resolve_without_raising(key: str) -> None:
    """Proves: STORY-014-AC-1

    Invariant (Hypothesis over every int-typed registry key): ``get_int`` resolves
    the declared default with no user-saved value and no run, coercing successfully
    and never raising.
    """
    # Arrange
    store = FakeAppSettingsStore()
    service = make_settings_service(store=store, event_bus=FakeEventBus())

    # Act
    resolved = service.get_int(key, run=None)

    # Assert
    assert resolved == coerce_int(DEFAULTS[key])


def test_per_run_overridable_is_a_subset_of_defaults() -> None:
    """Sanity check (no AC): the story explicitly calls out that every key in
    ``PER_RUN_OVERRIDABLE`` must also be a member of ``DEFAULTS`` — a per-run
    key with no in-code default would break the ``User-Saved -> Default``
    fallback the snapshot builder relies on.
    """
    # Assert
    assert DEFAULTS.keys() >= PER_RUN_OVERRIDABLE
