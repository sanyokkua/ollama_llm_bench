"""The concrete ``ModelCapabilitiesStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.5; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §4.6, §7.
"""

from collections.abc import Callable
import sqlite3
import threading

from ollama_llm_bench.backend.domain import (
    CapabilitySource,
    ModelCapability,
    ModelCapabilityRecord,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.errors import PersistenceError

__all__: list[str] = [
    "SqliteModelCapabilitiesStore",
]

_SELECT_CAPABILITY_COLUMNS = """
    SELECT provider_id, model_name, capability, supported, last_observed_at, observed_via, detail
    FROM model_capabilities
    WHERE provider_id = ? AND model_name = ?
    ORDER BY capability
"""

_UPSERT_CAPABILITY = """
    INSERT INTO model_capabilities (
        provider_id, model_name, capability, supported, last_observed_at, observed_via, detail
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (provider_id, model_name, capability) DO UPDATE SET
        supported = excluded.supported,
        last_observed_at = excluded.last_observed_at,
        observed_via = excluded.observed_via,
        detail = excluded.detail
"""


class SqliteModelCapabilitiesStore:
    """``ModelCapabilitiesStore`` over the single write connection and read-only factory.

    Satisfies the ``ModelCapabilitiesStore`` Protocol structurally. Every method
    wraps ``sqlite3.Error`` into ``PersistenceError``.
    """

    def __init__(
        self,
        *,
        write_conn: sqlite3.Connection,
        lock: threading.Lock,
        read_conn_factory: Callable[[], sqlite3.Connection],
    ) -> None:
        self._write_conn = write_conn
        self._lock = lock
        self._read_conn_factory = read_conn_factory

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return the cached capability records for one model.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute(_SELECT_CAPABILITY_COLUMNS, (provider_id, model_name))
            rows = cursor.fetchall()
            return tuple(_row_to_capability_record(row) for row in rows)
        except sqlite3.Error as exc:
            message = f"failed to list model capabilities for {provider_id!r}/{model_name!r}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Insert or update one capability record on the
        ``(provider_id, model_name, capability)`` primary key.

        Raises:
            PersistenceError: The underlying write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute(
                    _UPSERT_CAPABILITY,
                    (
                        record.provider_id,
                        record.model_name,
                        record.capability.value,
                        record.supported,
                        record.last_observed_at,
                        record.observed_via.value,
                        record.detail,
                    ),
                )
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = (
                    f"failed to upsert model capability {record.capability.value!r} "
                    f"for {record.provider_id!r}/{record.model_name!r}"
                )
                raise PersistenceError(message=message) from exc


def _row_to_capability_record(row: sqlite3.Row) -> ModelCapabilityRecord:
    """Assemble a ``ModelCapabilityRecord`` from one ``model_capabilities`` row."""
    return ModelCapabilityRecord(
        provider_id=row[0],
        model_name=row[1],
        capability=ModelCapability(row[2]),
        supported=row[3],
        last_observed_at=row[4],
        observed_via=CapabilitySource(row[5]),
        detail=row[6],
    )
