"""The ``AppSettingsStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.6.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import SettingKey

__all__: list[str] = [
    "AppSettingsStore",
]


class AppSettingsStore(Protocol):
    """The user-saved settings layer and the schema-version row.

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or a worker thread.
    """

    def get_setting(self, key: SettingKey) -> str | None:
        """Return one user-saved setting value, or ``None`` if unset.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Insert or update settings rows atomically.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        """Insert or update settings rows against an already-open transaction.

        Must be called only by a caller that already holds the write lock
        and has an open transaction on the shared write connection --
        used exclusively by ``backend.settings``'s ``SettingsAtomicWriter``.
        Ordinary callers use ``upsert_settings`` instead.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        """Delete every settings row and insert every key in ``values``,
        against an already-open transaction.

        Must be called only by a caller that already holds the write lock
        and has an open transaction on the shared write connection --
        used exclusively by ``SettingsAtomicWriter.reset_to_defaults``.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def list_settings(self) -> dict[SettingKey, str]:
        """Return every user-saved setting.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def get_schema_version(self) -> int:
        """Return the schema version recorded in ``app_meta``.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...
