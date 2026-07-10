"""The concrete ``AppSettingsStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.6.
"""

from collections.abc import Callable
import sqlite3
import threading

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra import Clock

__all__: list[str] = [
    "SqliteAppSettingsStore",
]


class SqliteAppSettingsStore:
    """``AppSettingsStore`` over the single write connection and read-only factory.

    Satisfies the ``AppSettingsStore`` Protocol structurally. Every method wraps
    ``sqlite3.Error`` into ``PersistenceError``.
    """

    def __init__(
        self,
        *,
        write_conn: sqlite3.Connection,
        lock: threading.Lock,
        read_conn_factory: Callable[[], sqlite3.Connection],
        clock: Clock,
    ) -> None:
        self._write_conn = write_conn
        self._lock = lock
        self._read_conn_factory = read_conn_factory
        self._clock = clock

    def get_setting(self, key: SettingKey) -> str | None:
        """Return one user-saved setting value, or ``None`` if unset.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            message = f"failed to read setting {key!r}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return None if row is None else str(row[0])

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Insert or update settings rows atomically.

        Raises:
            PersistenceError: The underlying write failed.
        """
        updated_at = self._clock.now_utc()
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                for key, value in values.items():
                    self._write_conn.execute(
                        "INSERT INTO app_settings (setting_key, setting_value, updated_at) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT(setting_key) DO UPDATE SET "
                        "setting_value = excluded.setting_value, "
                        "updated_at = excluded.updated_at",
                        (key, value, updated_at),
                    )
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to upsert app_settings rows"
                raise PersistenceError(message=message) from exc

    def list_settings(self) -> dict[SettingKey, str]:
        """Return every user-saved setting.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute("SELECT setting_key, setting_value FROM app_settings")
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            message = "failed to list app_settings"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return {str(row[0]): str(row[1]) for row in rows}

    def get_schema_version(self) -> int:
        """Return the schema version recorded in ``app_meta``.

        Raises:
            PersistenceError: The underlying read failed or the row is missing.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute("SELECT schema_version FROM app_meta WHERE id = 1")
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            message = "failed to read app_meta.schema_version"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        if row is None:
            message = "app_meta has no row with id = 1; the database was not initialised correctly"
            raise PersistenceError(message=message)
        return int(row[0])
