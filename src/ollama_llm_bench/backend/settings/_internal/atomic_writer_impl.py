"""The concrete SettingsAtomicWriter over the shared single-writer connection.

Source of truth: docs/v3_specification/06_Settings_Dialog/description.md §6, §9.
"""

import sqlite3
import threading

from ollama_llm_bench.backend.domain import ProviderConfig, SettingKey
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore

__all__: list[str] = ["SqliteSettingsAtomicWriter"]


class SqliteSettingsAtomicWriter:
    """Satisfies ``SettingsAtomicWriter`` over the shared write connection and lock."""

    def __init__(
        self,
        *,
        write_conn: sqlite3.Connection,
        lock: threading.Lock,
        providers_store: ProvidersStore,
        app_settings_store: AppSettingsStore,
    ) -> None:
        self._write_conn = write_conn
        self._lock = lock
        self._providers_store = providers_store
        self._app_settings_store = app_settings_store

    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None:
        """See SettingsAtomicWriter.save_all."""
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._providers_store.replace_providers_in_open_transaction(providers)
                self._app_settings_store.upsert_settings_in_open_transaction(settings_values)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to save provider catalog and settings atomically"
                raise PersistenceError(message=message) from exc

    def reset_to_defaults(
        self,
        *,
        bundled_providers: tuple[ProviderConfig, ...],
        all_default_settings: dict[SettingKey, str],
    ) -> None:
        """See SettingsAtomicWriter.reset_to_defaults."""
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._providers_store.replace_providers_in_open_transaction(bundled_providers)
                self._app_settings_store.replace_all_settings_in_open_transaction(
                    all_default_settings
                )
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to reset provider catalog and settings atomically"
                raise PersistenceError(message=message) from exc
