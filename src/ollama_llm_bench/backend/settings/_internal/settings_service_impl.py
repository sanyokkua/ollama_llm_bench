"""Concrete ``SettingsService`` implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8; ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md`` §2-3.
"""

from ollama_llm_bench.backend.domain import BenchmarkRun, SettingKey
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_SETTINGS_CHANGED,
    AppSettingsChangedEvent,
    EventBus,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings._internal.resolver import (
    coerce_bool,
    coerce_float,
    coerce_int,
    require_known_key,
    resolve_typed,
)


class SettingsServiceImpl:
    """The sole accessor for setting values (`08-C` §3).

    Resolves every read through the three-layer cascade shared with
    ``RunSnapshotBuilderImpl`` via ``_internal/resolver.py``. Writes go only to
    the user-saved layer and emit ``_app_settings_changed`` on every ``set``
    and ``upsert`` call.
    """

    def __init__(self, *, store: AppSettingsStore, event_bus: EventBus) -> None:
        self._store = store
        self._event_bus = event_bus

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        """Resolve a string setting. See ``SettingsService.get_str``."""
        require_known_key(key)
        return resolve_typed(key, run, self._store, str)

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        """Resolve a boolean setting. See ``SettingsService.get_bool``."""
        require_known_key(key)
        return resolve_typed(key, run, self._store, coerce_bool)

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        """Resolve an integer setting. See ``SettingsService.get_int``."""
        require_known_key(key)
        return resolve_typed(key, run, self._store, coerce_int)

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        """Resolve a float setting. See ``SettingsService.get_float``."""
        require_known_key(key)
        return resolve_typed(key, run, self._store, coerce_float)

    def set(self, key: SettingKey, value: str) -> None:
        """Write one value to the user-saved layer. See ``SettingsService.set``."""
        require_known_key(key)
        self._store.upsert_settings({key: value})
        self._event_bus.emit(
            SIGNAL_APP_SETTINGS_CHANGED, AppSettingsChangedEvent(changed_keys=(key,))
        )

    def upsert(self, values: dict[SettingKey, str]) -> None:
        """Write several values atomically. See ``SettingsService.upsert``.

        Every key is validated before anything is written — an unknown key
        anywhere in ``values`` aborts the whole call with no partial write.
        The emitted event's ``changed_keys`` are the keys passed to this call,
        not a diff against prior values.
        """
        for key in values:
            require_known_key(key)
        self._store.upsert_settings(values)
        self._event_bus.emit(
            SIGNAL_APP_SETTINGS_CHANGED,
            AppSettingsChangedEvent(changed_keys=tuple(values)),
        )
