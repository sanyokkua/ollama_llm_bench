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
