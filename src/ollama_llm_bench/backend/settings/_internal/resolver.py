"""Shared cascade resolution and type coercion.

Used by both ``SettingsServiceImpl`` and ``RunSnapshotBuilderImpl`` so the four-way
type-coercion branch and the layer cascade are implemented exactly once.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``
§2 (resolution order) and
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §8 (the
SPEC-110 coercion-failure rule).
"""

from collections.abc import Callable

import structlog

from ollama_llm_bench.backend.domain import BenchmarkRun, SettingKey
from ollama_llm_bench.backend.errors import ConfigurationError, ProgrammerError
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE

__all__: list[str] = [
    "coerce_bool",
    "coerce_float",
    "coerce_int",
    "require_known_key",
    "resolve_raw",
    "resolve_typed",
]

_logger = structlog.get_logger(__name__)


def require_known_key(key: SettingKey) -> None:
    """Raise ``ConfigurationError`` if ``key`` is not a member of the registry.

    Args:
        key: The dotted registry key to check.

    Raises:
        ConfigurationError: ``key`` is absent from ``DEFAULTS``.
    """
    if key not in DEFAULTS:
        raise ConfigurationError(message=f"unknown setting key: {key!r}")


def resolve_raw(
    key: SettingKey, run: BenchmarkRun | None, store: AppSettingsStore
) -> tuple[str, bool]:
    """Resolve one key's raw string value through the three-layer cascade.

    Args:
        key: The dotted registry key to resolve; must already be known.
        run: The run whose frozen snapshot to consult first, when ``key`` is
            per-run-overridable, or ``None`` to skip the snapshot layer.
        store: The user-saved layer.

    Returns:
        A tuple of ``(raw_value, from_snapshot)`` — ``from_snapshot`` is
        ``True`` only when the value came from ``run.settings_snapshot``, so
        the caller can apply the stricter (``ProgrammerError``-raising)
        coercion rule to snapshot-sourced values (SPEC-110).

    Raises:
        PersistenceError: The underlying user-saved-layer read failed.
    """
    if key in PER_RUN_OVERRIDABLE and run is not None:
        for entry in run.settings_snapshot:
            if entry.setting_key == key:
                return entry.setting_value, True
    saved = store.get_setting(key)
    if saved is not None:
        return saved, False
    return DEFAULTS[key], False


def coerce_bool(raw: str) -> bool:
    """Parse a registry-storage-form boolean string.

    Args:
        raw: The stored string, expected to be ``"true"`` or ``"false"``.

    Returns:
        The parsed boolean.

    Raises:
        ValueError: ``raw`` is neither ``"true"`` nor ``"false"``.
    """
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(f"not a boolean: {raw!r}")


def coerce_int(raw: str) -> int:
    """Parse a registry-storage-form integer string.

    Args:
        raw: The stored decimal-text integer.

    Returns:
        The parsed integer.

    Raises:
        ValueError: ``raw`` is not a valid base-10 integer.
    """
    return int(raw.strip())


def coerce_float(raw: str) -> float:
    """Parse a registry-storage-form float string.

    Args:
        raw: The stored decimal-text float.

    Returns:
        The parsed float.

    Raises:
        ValueError: ``raw`` is not a valid float.
    """
    return float(raw.strip())


def resolve_typed[T](
    key: SettingKey,
    run: BenchmarkRun | None,
    store: AppSettingsStore,
    coerce: Callable[[str], T],
) -> T:
    """Resolve and coerce one key, applying the SPEC-110 fallback rule.

    Args:
        key: The dotted registry key to resolve; must already be known.
        run: The run whose frozen snapshot to consult first, or ``None``.
        store: The user-saved layer.
        coerce: The type-specific parser (``coerce_bool``/``coerce_int``/
            ``coerce_float``), or ``str`` for a plain string read.

    Returns:
        The resolved, coerced value.

    Raises:
        ProgrammerError: A per-run snapshot value could not be coerced —
            snapshots are app-written from validated input and cannot
            legitimately be malformed.
        PersistenceError: The underlying user-saved-layer read failed.
    """
    raw, from_snapshot = resolve_raw(key, run, store)
    try:
        return coerce(raw)
    except ValueError as exc:
        if from_snapshot:
            raise ProgrammerError(
                message=f"per-run settings snapshot holds a malformed value for {key!r}: {raw!r}"
            ) from exc
        _logger.warning("setting_coercion_failed", key=key, raw_value=raw)
        return coerce(DEFAULTS[key])
